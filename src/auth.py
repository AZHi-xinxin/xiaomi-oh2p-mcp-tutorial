import hmac

class BearerGate:
    def __init__(self, app, token):
        self.app, self.expected = app, ('Bearer ' + token).encode('ascii')

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            supplied = [v for k, v in scope.get('headers', []) if k.lower() == b'authorization']
            if len(supplied) != 1 or not hmac.compare_digest(supplied[0], self.expected):
                await send({'type': 'http.response.start', 'status': 401,
                            'headers': [(b'content-type', b'application/json'),
                                        (b'www-authenticate', b'Bearer')]})
                await send({'type': 'http.response.body', 'body': b'{"error":"unauthorized"}'})
                return
        await self.app(scope, receive, send)
