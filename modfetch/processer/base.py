from modfetch.core import ModFetch


class BaseProcesser:
    def __init__(self, context: ModFetch) -> None:
        self.context = context

    async def process(self, project_info: dict, version: str) -> None:
        pass
