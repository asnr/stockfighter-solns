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


class APIResponseError(Exception):
    def __init__(self, status_code, error_msg=None):
        self.status_code = status_code
        self.error_msg = error_msg


class StockPurse:
    def __init__(self, venue, stock, account):
        self._venue = venue
        self._stock = stock
        self._account = account
        self._basis = 0
        self._stocks_held = 0
        self._last_fill_price = None
        self._open_asks = {}
        self._closed_asks = {}
        self._open_bids = {}
        self._closed_bids = {}


    def value(self):
        return self._basis + (self._last_fill_price * self._stocks_held)


    def basis(self):
        return self._basis


    def stocks_held(self):
        return self._stocks_held


    def buy(self, type, qty, price):
        resp = buy(self._venue, self._stock, self._account, type, qty, price)
        
        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])
        
        # Update internal values
        self._stocks_held += resp_json['totalFilled']
        
        for fill in resp_json['fills']:
            self._basis -= fill['price']*fill['qty']

        if len(resp_json['fills']) > 0:
            self._last_fill_price = resp_json['fills'][-1]['price']

        if resp_json['open']:
            self._open_bids[resp_json['id']] = resp_json
        else:
            self._closed_bids[resp_json['id']] = resp_json

        return resp_json


    def sell(self, type, qty, price):
        resp = sell(self._venue, self._stock, self._account, type, qty, price)
        
        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])
        
        # Update internal values
        self._stocks_held -= resp_json['totalFilled']
        
        for fill in resp_json['fills']:
            self._basis += fill['price']*fill['qty']

        if len(resp_json['fills']) > 0:
            self._last_fill_price = resp_json['fills'][-1]['price']

        if resp_json['open']:
            self._open_asks[resp_json['id']] = resp_json
        else:
            self._closed_asks[resp_json['id']] = resp_json

        return resp_json


    def cancel_all(self):
        ret = {'asks': {}, 'bids': {}}
        for id in self._open_bids:
            ret['bids'][id] = self.cancel(id)
        for id in self._open_asks:
            ret['asks'][id] = self.cancel(id)


    def cancel(self, id):
        if id in self._closed_asks or id in self._closed_bids:
            return()
        elif id not in self._open_asks and id not in self._open_bids:
            # Raise some kind of Error?
            return()

        if id in self._open_asks:
            order_to_cancel = self._open_asks[id]
            is_ask = True
        else:
            order_to_cancel = self._open_bids[id]
            is_ask = False

        # Send the cancel message
        resp = delete(self._venue, self._stock, id)

        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])

        # Update internal values
        qty_diff = resp_json['totalFilled'] - order_to_cancel['totalFilled']
        self._stocks_held += (-1)*qty_diff if is_ask else qty_diff
        
        prev_basis_change = 0
        for fill in order_to_cancel['fills']:
            prev_basis_change += fill['price']*fill['qty']

        new_basis_change = 0
        for fill in resp_json['fills']:
            new_basis_change += fill['price']*fill['qty']

        if prev_basis_change > new_basis_change:
            # Data inconsistency! Do something?
            pass

        basis_diff = new_basis_change - prev_basis_change
        self._basis += basis_diff if is_ask else (-1)*basis_diff

        if len(resp_json['fills']) > 0:
            self._last_fill_price = resp_json['fills'][-1]['price']

        if is_ask:
            self._closed_asks[id] = resp_json
        else:
            self._closed_bids[id] = resp_json

        return resp_json


    def quote(self):
        resp = quote(self._venue, self._stock)

        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])

        # Update internal values
        self._last_fill_price = resp_json['last']

        return resp_json


    def orderbook(self):
        resp = orderbook(self._venue, self._stock)

        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])

        # No internal value to update
        
        return resp_json



def quote(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/quote'
        .format(venue, stock))
    return(requests.get(url))

def orderbook(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}'
        .format(venue, stock))
    return(requests.get(url))


def order(venue, stock, account, type, qty, direction, price=None):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/orders'
        .format(venue, stock))
    body = {
        'account': account,
        'venue': venue,
        'stock': stock,
        'qty': qty,
        'direction': direction,
        'orderType': type,
    }
    if price is not None:
        body['price'] = price

    return(requests.post(url, json=body, headers=AUTH_HEADER))


def buy(venue, stock, account, type, qty, price=None):
    return order(venue, stock, account, type, qty, 'buy', price)

def sell(venue, stock, account, type, qty, price=None):
    return order(venue, stock, account, type, qty, 'sell', price)


def delete(venue, stock, order):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/orders/{}'
        .format(venue, stock, order))
    return(requests.delete(url, headers = AUTH_HEADER))

