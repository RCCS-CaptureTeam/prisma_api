from importlib.metadata import PackageNotFoundError, version as _version

try:
    __version__ = _version("prisma_api")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0+unknown"


from prisma_api.prisma_api import prisma_api as init        # Main prisma_api class for initialisation
from prisma_api.prisma_api_v2 import PrismaAPIv2             # v2 API client (also accessible as api.v2)
from prisma_api.config import update_dev_mode, update_dev_host_port, locate_config  # Config utility functions