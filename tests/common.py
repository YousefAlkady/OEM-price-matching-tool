from unittest.mock import patch

REQUESTS_PATH = 'odoo.addons.rapidapi_bdeel.models.rapidapi_abstract.requests'


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


def _tiny_png():
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), (200, 0, 0)).save(buf, format='PNG')
    return buf.getvalue()


TINY_PNG = _tiny_png()


class FakeBinaryResponse(FakeResponse):
    def __init__(self, content=TINY_PNG, status=200):
        super().__init__(status, {})
        self._content = content
        self.read_any = False

    @property
    def content(self):
        self.read_any = True
        return self._content

    def iter_content(self, chunk_size=65536):
        self.read_any = True
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i:i + chunk_size]

    def close(self):
        pass


def patch_router(routes):
    """Patch requests so each call returns the response whose key is a substring of the URL.

    routes: {url_substring: FakeResponse}. Unmatched URLs raise, so a test can never hit the network.
    Returns (patcher, mocked); mocked.calls lists the URLs requested.
    """
    patcher = patch(REQUESTS_PATH)
    mocked = patcher.start()
    mocked.calls = []

    def route(url, *args, **kwargs):
        mocked.calls.append(url)
        for fragment, response in routes.items():
            if fragment in url:
                if isinstance(response, list):
                    return response.pop(0) if len(response) > 1 else response[0]
                return response
        raise AssertionError(f"Unexpected HTTP call in test: {url}")

    mocked.get.side_effect = route
    mocked.post.side_effect = route
    import requests as real_requests
    mocked.exceptions = real_requests.exceptions
    return patcher, mocked


def load_data(name):
    import json
    import os
    path = os.path.join(os.path.dirname(__file__), 'data', name)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)
