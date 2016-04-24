from __future__ import print_function

import requests

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


class APISession:
    def __init__(self):
        self._session = requests.Session()
        self._https_url_base = 'https://api.stockfighter.io/ob/api'

    def quote(self, venue, stock):
        url = ('{}/venues/{}/stocks/{}/quote'
               .format(self._https_url_base, venue, stock))
        return self._session.get(url)

    def orderbook(self, venue, stock):
        url = ('{}/venues/{}/stocks/{}'
               .format(self._https_url_base, venue, stock))
        return self._session.get(url)

    def buy(self, venue, stock, account, type, qty, price=None):
        return self.order(venue, stock, account, type, qty, 'buy', price)

    def sell(self, venue, stock, account, type, qty, price=None):
        return self.order(venue, stock, account, type, qty, 'sell', price)

    def order(self, venue, stock, account, type, qty, direction, price=None):
        url = ('{}/venues/{}/stocks/{}/orders'
               .format(self._https_url_base, venue, stock))
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

        return(self._session.post(url, json=body, headers=AUTH_HEADER))

    def cancel_order(self, venue, stock, order):
        url = ('{}/venues/{}/stocks/{}/orders/{}'
               .format(self._https_url_base, venue, stock, order))
        return self._session.delete(url, headers=AUTH_HEADER)


class StockPurse:
    def __init__(self, venue, stock, account, position=0, basis=0):
        self._session = APISession()
        self._venue = venue
        self._stock = stock
        self._account = account
        self._basis = basis
        self._position = position
        self._last_fill_price = None
        self._orders = {}
        self._open_asks = set()
        self._closed_asks = set()
        self._open_bids = set()
        self._closed_bids = set()


    def value(self):
        return self._basis + (self._last_fill_price * self._position)

    def basis(self):
        return self._basis

    def position(self):
        return self._position

    def position_with_open_asks(self):
        open_ask_qty = sum(
            self._orders[id].qty_resting() for id in self._open_asks)
        return self.position() - open_ask_qty

    def position_with_open_bids(self):
        open_bid_qty = sum(
            self._orders[id].qty_resting() for id in self._open_bids)
        return self.position() + open_bid_qty

    def qty_filled(self, id):
        return self._orders[id].qty_filled()

    def _check_resp_ok_and_jsonify(self, resp):
        if resp.status_code != 200:
            raise APIResponseError(resp.status_code)

        resp_json = resp.json()

        if not resp_json['ok']:
            raise APIResponseError(resp.status_code, resp_json['error'])

        return resp_json

    def order(self, direction, type, qty, price=None):
        resp = self._session.order(
            self._venue, self._stock, self._account, type, qty, direction, price)
        
        resp_json = self._check_resp_ok_and_jsonify(resp)
        
        # None should be time request was sent
        order = Order(
            self._venue, self._stock, self._account, direction, type, qty,
            price, None, resp_json)

        # Update internal values
        self._position -= order.qty_sent()
        self._basis -= order.cost()

        last_fill_price = order.last_fill_price()
        if last_fill_price is not None:
            self._last_fill_price = last_fill_price

        self._orders[buy_order.id] = order

        if order.is_ask():
            if order.is_open():
                self._open_asks.add(order.id)
            else:
                self._closed_asks.add(order.id)
        else:
            if order.is_open():
                self._open_bids.add(order.id)
            else:
                self._closed_bids.add(order.id)

        return buy_order


    def buy(self, type, qty, price=None):
        return self.order('buy', type, qty, price)


    def sell(self, type, qty, price=None):
        return self.order('sell', type, qty, price)


    def cancel_all(self):
        ret = {'asks': {}, 'bids': {}}
        for id in self._open_bids:
            ret['bids'][id] = self.cancel(id)
        for id in self._open_asks:
            ret['asks'][id] = self.cancel(id)

        return ret


    def cancel(self, id):
        # Will throw KeyError if id new
        order_to_cancel = self._orders[id]

        if not order_to_cancel.is_open():
            return order_to_cancel

        # Send the cancel message
        resp = self._session.cancel_order(
            self._venue, self._stock, order_to_cancel.id)

        resp_json = self._check_resp_ok_and_jsonify(resp)

        cost_diff, qty_sent_diff = order_to_cancel.update(resp_json)

        # Update internal values
        self._basis -= cost_diff
        self._position -= qty_sent_diff
        
        last_fill_price = order_to_cancel.last_fill_price()
        if last_fill_price is not None:
            self._last_fill_price = last_fill_price

        if order_to_cancel.is_open():
            # Throw error?
            pass

        if order_to_cancel.is_ask():
            del self._open_asks[id]
            self._closed_asks.add(id)
        else:
            del self._open_bids[id]
            self._closed_bids.add(id)
            
        return order_to_cancel


    def quote(self):
        resp = self._session.quote(self._venue, self._stock)

        resp_json = self._check_resp_ok_and_jsonify(resp)

        # Update internal values
        self._last_fill_price = resp_json['last']

        return resp_json


    def orderbook(self):
        resp = self._session.orderbook(self._venue, self._stock)

        resp_json = self._check_resp_ok_and_jsonify(resp)

        # No internal values to update
        
        return resp_json


class Order:

    expected_top_keys = set(
            ['ok', 'id', 'ts', 'account', 'venue', 'symbol', 'direction',
             'orderType', 'originalQty', 'qty', 'price', 'fills',
             'totalFilled', 'open'])

    def __init__(self, req_venue, req_stock, req_account, req_direction,
                 req_type, req_qty, req_price, request_time, resp_json):
        # Validate response against request
        if req_account != resp_json['account']:
            pass
        #resp_json['venue']
        #resp_json['symbol']
        if req_direction != resp_json['direction']:
            pass
        if req_qty != resp_json['originalQty']:
            pass
        if req_price != resp_json['price']:
            pass
        if req_type != resp_json['orderType']:
            pass
        #resp_json['ts']

        # Check internal consistency of response
        sum_fill_qtys = sum(f['qty'] for f in resp_json['fills'])
        if resp_json['totalFilled'] != sum_fill_qtys:
            # log
            pass
        # check qty_outstanding

        # Check response doesn't contain extra data, for now only check top
        # level keys.
        unexpected_keys = [key for key in resp_json
                           if key not in self.expected_top_keys]
        if len(unexpected_keys) > 0:
            pass

        self.id = resp_json['id']
        self.req_time = req_time
        self.server_order_time = resp_json['ts']

        self.symbol = resp_json['symbol']
        self.venue = resp_json['venue']
        self.direction = resp_json['direction']
        self.type = resp_json['orderType']
        self.qty = resp_json['originalQty']
        #self.qty_outstanding = resp_json['qty']
        self.price = resp_json['price']
        self.account = resp_json['account']
        self.fills = resp_json['fills']
        self.total_filled = sum_fill_qtys
        self.open = resp_json['open']


    def is_open(self):
        return self.open

    def is_ask(self):
        return self.direction == 'sell'

    def cost(self):
        """Negative if ask, positive if bid"""
        abs_cost = sum(f['price'] * f['qty'] for f in self.fills)
        return -abs_cost if self.is_ask() else abs_cost

    def qty_sent(self):
        return self.total_filled if self.is_ask() else -self.total_filled

    def qty_filled(self):
        return self.total_filled

    def qty_resting(self):
        return self.qty - self.total_filled

    def last_fill_price(self):
        return self.fills[-1] if len(self.fills) > 0 else None

    def update(self, resp_json):
        """Returns 2-tuple: (cost_diff, qty_sent_diff)"""

        if not self.open:
            # Hmm I can get updates to closed orders by hitting either of the
            # 'status for all orders' endpoints
            pass

        # Check consistency with current state
        #'symbol'
        #'venue'
        if self.account != resp_json['account']:
            pass
        if self.direction != resp_json['direction']:
            pass
        if self.type != resp_json['orderType']:
            pass
        if self.qty != resp_json['originalQty']:
            pass
        if self.price != resp_json['price']:
            pass
        if any(old != new for old, new in zip(self.fills, resp_json['fills'])):
            pass

        new_cost_abs = sum(f['price'] * f['qty'] for f in resp_json['fills'])
        new_cost = -new_cost_abs if self.is_ask() else new_cost_abs
        cost_diff = new_cost - self.cost()

        sum_new_fill_qtys = sum(f['qty'] for f in resp_json['fills'])
        qty_diff = sum_new_fill_qtys - self.total_filled
        qty_sent_diff = qty_diff if self.is_ask() else -qty_diff

        self.fills = resp_json['fills']
        self.total_filled = sum_new_fill_qtys
        self.open = resp_json['open']

        return (cost_diff, qty_sent_diff)


def quote(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}/quote'
        .format(venue, stock))
    return(requests.get(url))

def orderbook(venue, stock):
    url = ('https://api.stockfighter.io/ob/api/venues/{}/stocks/{}'
        .format(venue, stock))
    return(requests.get(url))


