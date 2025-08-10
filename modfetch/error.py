import aiohttp


class ModFetchError(Exception):
    pass


class ModrinthError(ModFetchError):
    def __init__(self, msg: str, response: aiohttp.ClientResponse):
        super().__init__(msg)
        self.response = response
