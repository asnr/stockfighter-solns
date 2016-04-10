from __future__ import print_function

import requests
import time

def get_auth_key():
    with open('../AUTH_KEY') as fp:
        auth_key = fp.read().strip()
    return(auth_key)

AUTH_HEADER = {
    'X-Starfighter-Authorization':
        get_auth_key()
}


# class OrderResp:
    
#     def __init__(self, get_response):
#         self._raw_resp = get_response
        

def quote(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/quote'
        .format(venue, stock))
    return(requests.get(url))

def orderbook(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}'
        .format(venue, stock))
    return(requests.get(url))

def buy(venue, stock, account, type, qty, price):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/orders'
        .format(venue, stock))
    body = {
        'account': account,
        'venue': venue,
        'stock': stock,
        'qty': qty,
        'direction': 'buy',
        'orderType': type,
    }
    if (price is not None):
        body['price'] = price

    return(requests.post(url, json=body, headers = AUTH_HEADER))


def delete(venue, stock, order):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/orders/{}'
        .format(venue, stock, order))
    return(requests.delete(url, headers = AUTH_HEADER))

