from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("prisma_api")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"


from prisma_api.config import locate_config, update_dev_host_port, update_dev_mode
from prisma_api.prisma_api import prisma_api as init  # main client
from prisma_api.prisma_api_v2 import (  # v2 client (also api.v2) and upsert failure signals
    PrismaAPIv2,
    PrismaNewStructureWarning,
    PrismaRowErrorWarning,
    PrismaUnknownFieldsWarning,
    PrismaUpsertError,
)

__all__ = [
    "PrismaAPIv2",
    "PrismaNewStructureWarning",
    "PrismaRowErrorWarning",
    "PrismaUnknownFieldsWarning",
    "PrismaUpsertError",
    "__version__",
    "init",
    "locate_config",
    "update_dev_host_port",
    "update_dev_mode",
]
