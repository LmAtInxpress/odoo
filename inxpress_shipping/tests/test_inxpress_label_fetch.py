from odoo.tests.common import TransactionCase, tagged

from ..models.inxpress_client import InXpressClient


class _FakeClient:
    """Records calls; no HTTP. The dispatch URL fails, as an expired one does."""

    def __init__(self, fresh_response):
        self.fresh_response = fresh_response
        self.downloaded = []
        self.document_endpoint_called = False

    def download_label_url(self, url):
        self.downloaded.append(url)
        if url == "https://expired.invalid/label.pdf":
            raise RuntimeError("403 from S3")
        return b"%PDF-fresh"

    def get_label_url(self, shipment_id):
        return self.fresh_response

    def get_label(self, shipment_id):
        self.document_endpoint_called = True
        return b"%PDF-document-endpoint"


@tagged("post_install", "-at_install")
class TestInXpressLabelFetch(TransactionCase):
    """PUB-74: the re-presign is GET .../documents/label, which answers {type, url, expiresAt}."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        product = cls.env["product.product"].create({
            "name": "InXpress Delivery",
            "type": "service",
        })
        cls.carrier = cls.env["delivery.carrier"].create({
            "name": "InXpress Test",
            "delivery_type": "inxpress",
            "product_id": product.id,
            "inxpress_base_url": "https://example.invalid",
            "inxpress_api_token": "ixpx_test",
        })

    def test_expired_dispatch_url_falls_back_to_the_documents_url(self):
        client = _FakeClient({
            "type": "label",
            "url": "https://fresh.invalid/label.pdf",
            "expiresAt": "2026-10-13T20:30:00Z",
        })

        pdf = self.carrier._inxpress_fetch_label_bytes(
            client, 4926916, "https://expired.invalid/label.pdf")

        self.assertEqual(pdf, b"%PDF-fresh")
        self.assertEqual(client.downloaded, [
            "https://expired.invalid/label.pdf",
            "https://fresh.invalid/label.pdf",
        ])
        self.assertFalse(client.document_endpoint_called)

    def test_the_old_label_url_field_is_not_read(self):
        client = _FakeClient({"labelUrl": "https://fresh.invalid/label.pdf"})

        pdf = self.carrier._inxpress_fetch_label_bytes(
            client, 4926916, "https://expired.invalid/label.pdf")

        self.assertEqual(pdf, b"%PDF-document-endpoint")
        self.assertTrue(client.document_endpoint_called)

    def test_client_calls_the_documents_path(self):
        client = InXpressClient("https://example.invalid/", api_token="ixpx_test")
        paths = []
        client._get = lambda path: paths.append(path) or {}

        client.get_label_url(4926916)

        self.assertEqual(paths, ["/api/v3/integrations/shipments/4926916/documents/label"])
