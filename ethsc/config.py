"""Configuration data: Infura method prices in credits.

eth_blockNumber is not confirmed yet; check it against the dashboard.
"""

PRICES = {
    "eth_blockNumber": 80,  # не подтверждено, сверить с дашбордом
    "eth_getBlockReceipts": 1000,
    "eth_getCode": 80,
    "eth_getStorageAt": 80,
}

# The keyless second data source (phase 10).
PUBLICNODE_URL = "https://ethereum-rpc.publicnode.com"
