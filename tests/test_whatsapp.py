from app.integrations.whatsapp import WahaClient


class _FakeResp:
    def raise_for_status(self):
        return None


class _FakeHttpx:
    def __init__(self):
        self.calls = []

    def post(self, url, json=None, headers=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _FakeResp()


def test_waha_send_text():
    fake = _FakeHttpx()
    waha = WahaClient(base_url="http://waha:3000", session="default", api_key="secret", client=fake)
    waha.send_text("628111@c.us", "halo")
    call = fake.calls[-1]
    assert call["url"] == "http://waha:3000/api/sendText"
    assert call["json"] == {"session": "default", "chatId": "628111@c.us", "text": "halo"}
    assert call["headers"]["X-Api-Key"] == "secret"
