__version__ = "0.2.4"


from prisma_api.prisma_api import prisma_api as init        # Main prisma_api class for initialisation
from prisma_api.config import update_dev_mode, update_dev_host_port, locate_config  # Config utility functions