from unittest.mock import patch

REQUESTS_PATH = 'odoo.addons.rapidapi_bdeel.models.rapidapi_abstract.requests'


class FakeResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}

    def json(self):
        return self._body


def patch_http(*responses):
    """Patch requests.get/post to return the given responses in order. Returns (patcher, mock_get, mock_post)."""
    patcher = patch(REQUESTS_PATH)
    mocked = patcher.start()
    queue = list(responses)

    def next_response(*args, **kwargs):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    mocked.get.side_effect = next_response
    mocked.post.side_effect = next_response
    # keep the real exception classes so `except requests.exceptions...` still works
    import requests as real_requests
    mocked.exceptions = real_requests.exceptions
    return patcher, mocked
