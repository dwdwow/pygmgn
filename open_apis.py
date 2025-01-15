import asyncio
from enum import Enum
from typing import TypeVar, TypedDict

import requests


base_url = 'https://www.gmgn.cc'


Data = TypeVar('Data')


ResponseData = TypedDict('ResponseData', {
    'code': int,
    'data': Data,
    'msg': str, 
})


Kline = TypedDict('Kline', {
    'open': str,
    'close': str,
    'high': str,
    'low': str,
    'time': str,
    'volume': str
})

class Network(Enum):
    SOLANA = 'sol'
    ETHEREUM = 'eth'
    

class Period(Enum):
    ONE_HOUR = '1h'


async def get_klines(network: Network, token: str, period: Period, from_seconds: int, to_seconds: int) -> list[Kline]:
    url = f'{base_url}/defi/quotation/v1/tokens/kline/{network.value}/{token}?resolution={period.value}&from={from_seconds}&to={to_seconds}'
    resp = await asyncio.to_thread(requests.get, url)
    status_code = resp.status_code
    if status_code != 200:
        raise Exception(f'GMGN Open API Error: {status_code}')
    data = ResponseData(resp.json())
    code = data['code'] 
    if code != 0:
        raise Exception(f'GMGN Open API Error: {code} - {data["msg"]}')
    return data['data']


if __name__ == '__main__':
    klines = asyncio.run(get_klines(Network.SOLANA, 'HeLp6NuQkmYB4pYWo2zYs22mESHXPQYzXbB8n4V98jwC', Period.ONE_HOUR, 1715731200, 1715734800))
    print(klines)