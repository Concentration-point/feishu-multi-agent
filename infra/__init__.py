"""infra/ — 与业务无关的基础设施层。

目前只包含 HttpClientProvider，用于在进程内复用 httpx.AsyncClient，
避免每次请求都新建连接池。
"""
