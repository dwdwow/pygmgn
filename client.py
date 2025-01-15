import asyncio
import base64
from enum import Enum
import getpass
import time
from typing import TypeVar, TypedDict

import requests

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction

from loguru import logger


Data = TypeVar('Data')

ResponseData = TypedDict('ResponseData', {
    'code': int,
    'data': Data,
    'msg': str, 
    'tid': str
})


SwapRouteQuote = TypedDict('SwapRouteQuote', {
    'inputMint': str,
    'inAmount': str,
    'outputMint': str,
    'outAmount': str,
    'otherAmountThreshold': str,
    'swapMode': str,
    'slippageBps': int,
    'platformFee': any,
    'priceImpactPct': str,
    'routePlan': list,
    'contextSlot': int,
    'timeTaken': float
})

SwapRouteQuote = TypedDict('SwapRouteQuote', {
    'inputMint': str,
    'inAmount': str, 
    'outputMint': str,
    'outAmount': str,
    'otherAmountThreshold': str,
    'swapMode': str,
    'slippageBps': int,
    'platformFee': any,
    'priceImpactPct': str,
    'routePlan': list,
    'contextSlot': int,
    'timeTaken': float
})


SwapRouteRawTx = TypedDict('SwapRouteRawTx', {
    'swapTransaction': str,
    'lastValidBlockHeight': int, 
    'prioritizationFeeLamports': int,
    'recentBlockhash': str
})


SwapRouteResponse = TypedDict('SwapRouteResponse', {
    'quote': SwapRouteQuote,
    'raw_tx': SwapRouteRawTx
})


SubmitTxResponse = TypedDict('SubmitTxResponse', {
    'hash': str
})


SubmitAntiMevTxResponse = TypedDict('SubmitAntiMevTxResponse', {
    'bundle_id': str,
    'last_valid_block_number': int,
    'tx_hash': str
})


"""
Represents the status of a transaction.

Attributes:
    success (bool): Whether the transaction was successfully added to the blockchain. True if successful.
    failed (bool): Whether the transaction was added to the blockchain but failed. True if failed.
    expired (bool): Whether the transaction has expired. If expired=True and success=False, 
                    the transaction has expired and needs to be resubmitted. Transactions typically
                    expire after 60 seconds.
"""
TxStatusResponse = TypedDict('TxStatusResponse', {
    'success': bool,
    'failed': bool,
    'expired': bool,
    'err': any,
    'err_code': str,
})


tx_base_url = "https://gmgn.ai/defi/router/v1"


class SwapMode(Enum):
    EXACT_IN = "ExactIn"
    EXACT_OUT = "ExactOut"


class GMGNSolClient:

    def __init__(self, *, pvk_base58: str=None, sol_pvk_file_path: str=None, aes_256_hex_key: str=None):
        if sol_pvk_file_path:
            with open(sol_pvk_file_path, 'r') as f:
                pvk_base58 = f.read()
                pvk_base58 = pvk_base58.strip('\t\n\r ')
        if not aes_256_hex_key:
            aes_256_hex_key = getpass.getpass('Please input decrypt aes_256_key for gmgn client solana encrypted private key (if not encrypted, please input empty): ')
        if aes_256_hex_key:
            if len(aes_256_hex_key) != 64:
                raise Exception("GMGN_SOL_CLIENT: Hex Password must be 64 characters long")
            encrypted_bytes = base64.b64decode(pvk_base58.encode('utf-8'))
            iv = encrypted_bytes[:AES.block_size]
            ciphertext = encrypted_bytes[AES.block_size:]
            cipher = AES.new(bytes.fromhex(aes_256_hex_key), AES.MODE_CBC, iv)
            decrypted_bytes = unpad(cipher.decrypt(ciphertext), AES.block_size)
            pvk_base58 = decrypted_bytes.decode('utf-8')
        self._pvk = pvk_base58
        self.signer = Keypair.from_base58_string(pvk_base58)
        self.signer_address = str(self.signer.pubkey())
        
    def sign_raw_tx(self, base64_tx: str) -> str:
        tx_bytes = base64.b64decode(base64_tx)
        tx = VersionedTransaction.from_bytes(tx_bytes)
        signed_tx = VersionedTransaction(tx.message, [self.signer])
        return base64.b64encode(bytes(signed_tx)).decode('utf-8')

    @classmethod
    async def get(cls, other_path: str, **kwargs) -> ResponseData:    
        url = f'{tx_base_url}/{other_path.strip("/")}'
        resp = await asyncio.to_thread(requests.get, url, kwargs)
        status_code = resp.status_code
        if status_code != 200:
            raise Exception(f'GMGN_SOL_CLIENT: GET Error {status_code}, {url}')
        data = ResponseData(resp.json())
        if not isinstance(data, dict):
            raise Exception(f'GMGN_SOL_CLIENT: Response data is not a dict: {data}, {url}')
        if data['code'] != 0:
            raise Exception(f'GMGN_SOL_CLIENT: GET Error {data["code"]} - {data["msg"]}, {url}')
        return data['data']
    
    @classmethod
    async def post(cls, other_path: str, body: dict) -> ResponseData:
        url = f'{tx_base_url}/{other_path.strip("/")}'
        resp = await asyncio.to_thread(requests.post, url, json=body)
        status_code = resp.status_code
        if status_code != 200:
            raise Exception(f'GMGN_SOL_CLIENT: POST Error {status_code}, {url}')
        data = ResponseData(resp.json())
        if not isinstance(data, dict):
            raise Exception(f'GMGN_SOL_CLIENT: Response data is not a dict: {data}, {url}')
        if data['code'] != 0:
            raise Exception(f'GMGN_SOL_CLIENT: POST Error {data["code"]} - {data["msg"]}, {url}')
        return data['data']
    
    async def get_swap_route(self,
                              * ,
                            token_in_address: str,
                            token_out_address: str,
                            in_amount: str,
                            slippage: float,
                            swap_mode: SwapMode,
                            fee: float=0.00001,
                            from_address: str=None,
                            is_anti_mev: bool=False,
                            partner: str=None) -> SwapRouteResponse:
        """Get swap route from GMGN API.

        Args:
            token_in_address (str): Input token address
            token_out_address (str): Output token address 
            in_amount (str): Input amount in lamports (e.g. "100000000" = 0.1 SOL)
            slippage (float): Slippage tolerance percentage (e.g. 10 = 10%)
            swap_mode (SwapMode): Swap mode enum value
            fee (float, optional): Network priority and RPC node tip fees in SOL. Default 0.00001.
                                 GMGN automatically allocates between node tips and priority fees.
                                 Must be >= 0.002 if is_anti_mev=True
            from_address (str, optional): Source wallet address. Defaults to signer address
            is_anti_mev (bool, optional): Whether to use anti-MEV protection. Defaults to False
            partner (str, optional): Partner identifier. Defaults to None

        Returns:
            SwapRouteResponse: Swap route details from API

        Raises:
            Exception: If fee is greater than 5 SOL
        """

        if fee > 5:
            raise Exception('GMGN_SOL_CLIENT: Fee must be less than 5')
        params = locals()
        del params['self']
        if not is_anti_mev:
            params.pop('is_anti_mev')
        if not partner:
            params.pop('partner')
        if not from_address:
            params['from_address'] = self.signer_address
        return await self.get('sol/tx/get_swap_route', **params)
    
    async def submit_tx(self, signed_tx: str) -> SubmitTxResponse:
        return await self.post('sol/tx/submit_signed_transaction', body={'signed_tx': signed_tx})
    
    async def submit_anti_mev_tx(self, signed_tx: str, from_address: str=None) -> SubmitAntiMevTxResponse:
        if not from_address:
            from_address = self.signer_address
        return await self.post('sol/tx/submit_tx_anti_mev_mode', body={'signed_tx': signed_tx, 'from_address': from_address})

    @classmethod
    async def get_tx_status(cls, hash: str, last_valid_height: int) -> TxStatusResponse:
        return await cls.get('sol/tx/get_transaction_status', hash=hash, last_valid_height=last_valid_height)
    
    @classmethod
    async def wait_tx_status(cls, hash: str, last_valid_height: int, fetch_interval_seconds: float=0.4, timeout_seconds: float=60) -> TxStatusResponse:
        """Wait for transaction status from GMGN API.

        Args:
            hash (str): Transaction hash
            last_valid_height (int): Last valid block height for transaction
            fetch_interval_seconds (float, optional): Interval between status checks in seconds. Defaults to 0.4, because solana block update interval is 0.4 seconds.
            timeout_seconds (float, optional): Maximum time to wait for status in seconds. Defaults to 60.

        Returns:
            TxStatusResponse: Transaction status details from API

        Raises:
            Exception: If transaction status not found after timeout period
        """
        start_time = time.time()
        while time.time() - start_time < timeout_seconds:
            try:
                status = await cls.get_tx_status(hash, last_valid_height)
                if status['success'] or status['failed'] or status['expired']:
                    return status
            except Exception as e:
                logger.error(f'GMGN_SOL_CLIENT: Waiting for tx status error: {e}')
            await asyncio.sleep(fetch_interval_seconds)
        raise Exception(f'GMGN_SOL_CLIENT: Transaction {hash} status not found after {timeout_seconds} seconds')
    
    async def swap(self,
                      * ,
                    token_in_address: str,
                    token_out_address: str,
                    in_amount: str, # unit is lamports, 100000000=0.1SOL
                    slippage: float, # 10=10%
                    swap_mode: SwapMode,
                    fee: float,
                    from_address: str=None,
                    is_anti_mev: bool=False,
                    partner: str=None,
                    wait_tx_fetch_interval_seconds: float=0.4,
                    wait_tx_timeout_seconds: float=60) -> tuple[SwapRouteResponse | None, SubmitTxResponse | SubmitAntiMevTxResponse | None, TxStatusResponse | None]:
        """Perform a token swap on Solana using GMGN API.

        Args:
            token_in_address (str): Address of input token
            token_out_address (str): Address of output token 
            in_amount (str): Amount of input token in lamports (e.g. "100000000" = 0.1 SOL)
            slippage (float): Maximum allowed slippage percentage (e.g. 10 = 10%)
            swap_mode (SwapMode): EXACT_IN or EXACT_OUT swap mode
            fee (float): Network priority and RPC node tip fees in SOL (e.g. 0.00001). GMGN automatically allocates between 
                        node tips and priority fees. Must be >= 0.002 if is_anti_mev=True.
            from_address (str, optional): Source address. Defaults to signer address if not provided.
            is_anti_mev (bool, optional): Whether to use anti-MEV protection. Defaults to False.
            partner (str, optional): Partner identifier. Defaults to None.
            wait_tx_fetch_interval_seconds (float, optional): Interval between status checks in seconds. Defaults to 0.4.
            wait_tx_timeout_seconds (float, optional): Maximum time to wait for status in seconds. Defaults to 60.

        Returns:
            tuple[SwapRouteResponse | None, SubmitTxResponse | SubmitAntiMevTxResponse | None, TxStatusResponse | None]: 
                Tuple containing:
                - Quote/route information
                - Transaction submission response
                - Transaction status response

        Raises:
            Exception: If transaction status cannot be retrieved within timeout period
        """

        params = locals()
        del params['self']
        del params['wait_tx_fetch_interval_seconds']
        del params['wait_tx_timeout_seconds']
        quote = await self.get_swap_route(**params)
        unsigned_tx = quote['raw_tx']['swapTransaction']
        signed_tx = self.sign_raw_tx(unsigned_tx)
        last_valid_height = quote['raw_tx']['lastValidBlockHeight']
        tx_hash = None
        if not is_anti_mev:
            sub_resp = await self.submit_tx(signed_tx)
            tx_hash = sub_resp['hash']
        else:
            sub_resp = await self.submit_anti_mev_tx(signed_tx)
            tx_hash = sub_resp['tx_hash']
        status_resp = await self.wait_tx_status(tx_hash, last_valid_height, wait_tx_fetch_interval_seconds, wait_tx_timeout_seconds)
        return quote, sub_resp, status_resp


if __name__ == '__main__':
    import os
    home_dir = os.path.expanduser('~')
    pvk_file_path = os.path.join(home_dir, 'test_tokens', 'sol_test_pvk')
    client = GMGNSolClient(sol_pvk_file_path=pvk_file_path)
    print('signer address')
    print(client.signer_address)
    
    token_in_address='So11111111111111111111111111111111111111112'
    token_out_address='HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC'
    in_amount='10000000'
    slippage=10
    swap_mode=SwapMode.EXACT_IN
    fee=0.0001
    
    quote, sub_resp, status_resp = asyncio.run(client.swap(
        token_in_address=token_in_address,
        token_out_address=token_out_address,
        in_amount=in_amount,
        slippage=slippage,
        swap_mode=swap_mode,
        fee=fee,
    ))
    print('quote')
    print(quote)
    print('sub_resp')
    print(sub_resp)
    print('status_resp')
    print(status_resp)
