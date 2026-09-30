# Fixtures

Verbatim Ethereum mainnet data fetched from Infura (free tier) on 2026-09-28, plus
Sourcify-verified ABIs. Tests read these files and never open the network.

`code_*.hex` is the `result` string of `eth_getCode`, verbatim (`0x` + hex, no
newline). Decode with `bytes.fromhex(text.strip()[2:])`.

| file | address | why |
|---|---|---|
| `code_weth9.hex` | 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2 | WETH9: 11 published selectors, bzzr0 metadata, solc 0.4.19 |
| `code_usdt.hex` | 0xdAC17F958D2ee523a2206206994597C13D831ec7 | TetherToken: 32 selectors of a large contract |
| `code_univ2_usdc_weth.hex` | 0xB4e16d0168e52d35CaCD2c6185b44281Ec28C9Dc | UniswapV2Pair USDC/WETH: L0 |
| `code_univ2_weth_usdt.hex` | 0x0d4a11d5EEaaC28EC3F61d100daF4d40471f1852 | UniswapV2Pair WETH/USDT: byte-identical to the above |
| `code_univ3_usdc_weth_005.hex` | 0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640 | UniswapV3Pool: L1, immutables differ (74 bytes, PUSH32 only) |
| `code_univ3_pool_e0554a47.hex` | 0xe0554a476a092703abdb3ef35c80e0d76d32939f | UniswapV3Pool, second deployment of the same factory |
| `code_launchtoken_4e67db19.hex` | 0x4e67db19044549ff420860834c91b45bad298722 | LaunchToken (Sourcify exact match): L1, 3 PUSH32 differ |
| `code_launchtoken_40676634.hex` | 0x40676634577a95739251af92ded22ef943b73813 | LaunchToken, second deployment, 58 bytes differ |
| `code_clone_270df012.hex` | 0x270df01200e2f9fffd1c3d56f5b0a4b1c3eaaa5f | EIP-1167 clone of 0x4181f370… (HolderDistributor) |
| `code_clone_3b2fac8e.hex` | 0x3b2fac8e18e9d354cf1f4770ad0e80b797095a2d | EIP-1167 clone of the same implementation |
| `code_clone_2ca7b61b.hex` | 0x2ca7b61b23b15e75ac7ab60dd6f627895d64a46e | EIP-1167 clone of 0x8b72b9b8… (LaunchToken) |
| `code_7702_04cfab85.hex` | 0x04cfab854b82159745eead5ed4ad148645e1173b | EIP-7702 delegated EOA, `ef0100` + delegate |
| `code_proxy_seed_0c010533.hex` | 0x0c0105334a50db16b51b2911c9956539753a2cf8 | TransparentUpgradeableProxy seed of the live 30.09 base (2059 bytes, 5 admin selectors); `is_std_proxy` True (EIP-1967 impl slot); not `mutable_delegatecall`; caused 380 false recheck alerts before phase 9 |
| `code_proxy_046eee2c.hex` | 0x046eee2cc3188071c02bfc1745a6b17c656e3f3d | a second, distinct standard EIP-1967 proxy of the live base (2227 bytes, 0 selectors); `is_std_proxy` True; `similarity` to the seed proxy is 0.0 |
| `code_belle.hex` | 0x34c6211621f2763c60eb007dc2ae91090a2d22f6 | Security seed: BELLE. Etherscan: "This token is reported to be a honeypot token"; creator tagged "BELLE Honeypot Rug Pull" |
| `code_belle_copy_46cadea5.hex` | 0x46cadea509dc3d3c96a11fb61ab8b222f5238f0a | same deployer 0xf80f6fa4…, nonce 0 (WHALE) |
| `code_belle_copy_2141be5f.hex` | 0x2141be5f2afa674c94167ab167a478a56cb539f5 | same deployer, nonce 1 |
| `code_belle_copy_1807090d.hex` | 0x1807090dd15a6f58e00fd769e32ebf20ee610385 | same deployer, nonce 5 (ALPHA, Sourcify exact match, BotBlacklist) |
| `code_belle_copy_6411bed8.hex` | 0x6411bed82614b91ef655d82486e0bd3a13d2eb8c | same deployer, nonce 13 |
| `receipts_26077729.json` | block 26077729 (0x18dea21) | verbatim `eth_getBlockReceipts` response: 218 receipts, 626 logs, 1 deploy |
| `codes_26077729.json` | its 206 candidates | `{address: eth_getCode result at block 0x18dea21}`, sorted; 59 are `0x` |
| `rpc_429.json` | – | status, headers and verbatim body of a rate-limited Infura request |
| `abi_*.sourcify.json` | WETH9, USDT, UniswapV2Pair, BELLE | ABI from sourcify.dev, the independent source of the selector lists |

The BELLE copies were found by computing the CREATE addresses of the deployer's
nonces 0..76 and fetching their code. Only five have code.
