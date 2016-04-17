from __future__ import print_function

import time
import websocket

from ws4py.client.threadedclient import WebSocketClient
#from ws4py.client import WebSocketBaseClient

from websock import Executions

from lib import *

# stu hunter - Migration Suite

account = 'TMB8425913'
venue = 'CPREX'
stock = 'TBM'

purse = StockPurse(venue, stock, account)

def asymmetric_maker(stock_purse, num_rounds=30, wait_secs=2, qty_tolerance=350,
                     tolerance_adjust=1000, qty_marks=(20, 100, 400),
                     price_delta_fallback=100, qtys=(20, 100, 100)):
    '''Every round, get orberbook and make orders with prices based on quantities
    in the orderbook vs. `qty_marks` argument. For example, at qty_mark=(50,),
    one sell order will be issued that round at the price you need to buy the
    first 50 stocks on the last orderbook retrieved, and a similar buy order
    will be also be placed. If the absolute number of stocks held goes above by
    a multiple n of `qty_tolerance`, the prices for the next orders in that
    direction will be moved n*`tolerance_adjust` in that direction.'''

    best_ask_price = None
    best_bid_price = None
    for round in range(num_rounds):
        print('')
        print('######## Round {} ########'.format(round + 1))

        probe_book = get_probe_orderbook(stock_purse)
        if probe_book is None:
            print('Couldn\'t get a probe orderbook! Exiting...')
            return

        print('')

        ask_prices = price_till_qty(probe_book['asks'], qty_marks,
                                    price_delta_fallback, are_bids=False)
        bid_prices = price_till_qty(probe_book['bids'], qty_marks,
                                    price_delta_fallback, are_bids=True)

        stocks_held = stock_purse.stocks_held()
        # Note price_adjust always positive
        price_adjust = (abs(stocks_held) // qty_tolerance) * tolerance_adjust
        if stocks_held < -qty_tolerance:
            ask_prices = [price + price_adjust for price in ask_prices]
        elif stocks_held > qty_tolerance:
            bid_prices = [max(price - price_adjust, 0) for price in bid_prices]

        # Send bid orders
        for price, qty in zip(bid_prices, qtys):
            print(('Bidding price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                buy_resp = stock_purse.buy('limit', qty=qty, price=price)
            except APIResponseError as e:
                buy_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                print(' 200 OK, filled {} stocks, ID {}'
                      .format(buy_resp['totalFilled'], buy_resp['id']))

        # Send ask orders
        for price, qty in zip(ask_prices, qtys):
            print(('Asking price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                sell_resp = stock_purse.sell('limit', qty=qty, price=price)
            except APIResponseError as e:
                sell_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                print(' 200 OK, filled {} stocks, ID {}'
                      .format(sell_resp['totalFilled'], sell_resp['id']))

        time.sleep(wait_secs)

        cancelled_orders = stock_purse.cancel_all()

        print('\nAt round end, stocks held: {}, basis: {}, NAV: {}.'
              .format(stock_purse.stocks_held(), stock_purse.basis(),
                      stock_purse.value()))


def price_till_qty(orders, qtys, price_delta_fallback, are_bids):
        if len(orders) == 0 or len(qtys) == 0:
            return None

        # Make sure sign of price_delta_fallback is right
        if (are_bids and price_delta_fallback > 0) or \
           (not are_bids and price_delta_fallback < 0):
            price_delta_fallback *= -1

        prices = []
        qty_so_far = 0
        last_price = None
        qty_idx, order_idx = (0, 0)

        while qty_idx < len(qtys) and order_idx < len(orders):
            if qty_so_far >= qtys[qty_idx]:
                prices.append(max(last_price, 0))
                qty_idx += 1
            else:                
                qty_so_far += orders[order_idx]['qty']
                last_price = orders[order_idx]['price']
                order_idx += 1

        while qty_idx < len(qtys):
            if qty_so_far < qtys[qty_idx]:
                last_price += price_delta_fallback
            prices.append(max(last_price, 0))
            qty_idx += 1

        return prices


def simple_market_maker(stock_purse, num_rounds, lag, qty_tolerance,
                        qtys=(100, 100), price_deltas=(25, 75)):
    '''Every round, the price midpoint is found by getting a quote and then
    adjusted based on the number of stocks currently held. The prices of the
    bids and asks are then offset by `price_deltas` from the midpoint (in both
    directions) at the quantities specified by `qtys`.'''
    best_ask_price = None
    best_bid_price = None
    for round in range(num_rounds):
        print('')
        print('######## Round {} ########'.format(round + 1))

        probe_quote = get_probe_quote(stock_purse)
        if probe_quote is None:
            print('Couldn\'t get a probe quote! Exiting...')
            return

        print('')

        best_ask_price = probe_quote['ask']
        best_bid_price = probe_quote['bid']

        stocks_held = stock_purse.stocks_held()
        price_mid_point = (best_ask_price + best_bid_price) // 2
        # Adjust for quantity of stock held; we want to hold as close to
        # zero stock as possible.
        adjusted_mid_point = price_mid_point + \
            int((stocks_held / float(qty_tolerance)) *
                (price_mid_point - best_ask_price))

        bid_prices = tuple(adjusted_mid_point - p for p in price_deltas)
        ask_prices = tuple(adjusted_mid_point + p for p in price_deltas)

        print('Best ask price: {:>5}, best bid price: {:5}, midpoint: {:5}'
              .format(best_ask_price, best_bid_price, price_mid_point))
        print('Adjusted mid point: {:>5}  (stocks held: {})'
              .format(adjusted_mid_point, stocks_held))
        print('')

        # Send bid orders
        for price, qty in zip(bid_prices, qtys):
            print(('Bidding price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                buy_resp = stock_purse.buy('limit', qty=qty,
                                           price=price)
            except APIResponseError as e:
                buy_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                print(' 200 OK')
                print_fills(buy_resp['fills'], n=2)
            

        # Send ask order
        for price, qty in zip(ask_prices, qtys):
            print(('Asking price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                sell_resp = stock_purse.sell('limit', qty=qty,
                                             price=price)
            except APIResponseError as e:
                sell_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                print(' 200 OK')
                print_fills(sell_resp['fills'], n=2)

        time.sleep(lag)

        cancelled_orders = stock_purse.cancel_all()

        print('\nAt round end, stocks held: {}, basis: {}, value: {}.'
              .format(stock_purse.stocks_held(), stock_purse.basis(),
                      stock_purse.value()))


def get_probe_quote(stock_purse, max_retries=10):
    probe_quote = None
    for attempt in range(max_retries):
        print('Issue probing quote...', end='')
        try:
            probe_quote = stock_purse.quote()
        except APIResponseError as e:
            print(' {}'.format(print_order_err(e)))
        else:
            print(' 200 OK, last price: {}'.format(probe_quote['last']))
            if 'ask' not in probe_quote or 'bid' not in probe_quote:
                probe_quote = None
                continue
            else:
                break

    return probe_quote


def get_probe_orderbook(stock_purse, max_retries=10):
    probe_orderbook = None
    for attempt in range(max_retries):
        print('GET orderbook...', end='')
        try:
            probe_orderbook = stock_purse.orderbook()
        except APIResponseError as e:
            print(' {}'.format(print_order_err(e)))
        else:
            asks = probe_orderbook['asks']
            bids = probe_orderbook['bids']
            print(' 200 OK, number bids: {}, asks: {}'
                  .format(0 if bids is None else len(bids),
                          0 if asks is None else len(asks)))
            if asks is None or bids is None or \
               len(asks) == 0 or len(bids) == 0:
                probe_orderbook = None
                continue
            else:
                break

    return probe_orderbook


def print_order_err(e):
    if e.error_msg is None:
        print('status code: {}'.format(e.status_code))
    else:
        print('status code: {}, message {}'
              .format(e.status_code, e.error_msg))

def print_fills(fills, n=3):
    if len(fills) == 0:
        print('  received 0 fills.')
    elif len(fills) <= n:
        print('  received {} fills:'.format(len(fills)))
    else:
        print('  top {} of {} fills:'.format(n, len(fills)))
    for fill in fills[:n]:
        print('    price:{price:>6}, qty:{qty:>5}'
                .format(price=fill['price'], qty=fill['qty']))


def rolling_orderbook(secs_between_updates, num_orders_visible):
    def print_order(order):
        print('  Price:{price:>9}, Qty:{qty:>6}'
                .format(price=order['price'], qty=order['qty']))

    try:
        while True:
            r = orderbook(venue, stock)
            if (r.status_code != 200):
                print('Received status code {}'.format(r.status_code))
                break
            r_json = r.json()
            print('\nORDER BOOK as at {}'.format(r_json['ts']))
            
            if r_json['asks'] is None:
                print('  No asks')
            else:
                map(print_order, reversed(r_json['asks'][:num_orders_visible]))
            
            print('                ...')
            
            if r_json['bids'] is None:
                print('  No bids')
            else:
                map(print_order, r_json['bids'][:num_orders_visible])

            time.sleep(secs_between_updates)        
    except KeyboardInterrupt:
        pass


### Fooling around with websockets



class DummyClient(WebSocketClient):
    def opened(self):
        print('*******  OPEN  *******')

    def closed(self, code, reason=None):
        print('******* CLOSED *******')
        print('Code: {}, reason: {}'.format(code, reason))

    def received_message(self, m):
        if m.is_text:
            print('RECEIVED MESSAGE:')
            print(m)
        else:
            print('RECEIVED NONTEXT MESSAGE')


def rolling_fills():
    url = ('wss://api.stockfighter.io/ob/api/ws/{}/venues/{}/executions'
               .format(account, venue, stock))
    try:
        ws = DummyClient(url)
        ws.connect()
        ws.run_forever()
    except KeyboardInterrupt:
        ws.close()


def rolling_fills1():
    def on_message(ws, message):
        print('MESSAGE RECEIVED:')
        print(message)
    def on_data(ws, message, data_type, continue_bool):
        print('DATA RECEIVED:')
        print(message)
    def on_error(ws, error):
        print('ERROR:')
        print(error)
    def on_open(ws):
        print('*******  OPEN  *******')
    def on_close(ws):
        print('******* CLOSED *******')

    try:
        url = ('wss://api.stockfighter.io/ob/api/ws/{}/venues/{}/executions/stocks/{}'
               .format(account, venue, stock))
        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(url,
                                    on_open=on_open, on_message=on_message,
                                    on_error=on_error, on_close=on_close,
                                    on_data=on_data)
        ws.run_forever()
    except KeyboardInterrupt:
        pass


def rolling_quotes1():
    def on_message(ws, message):
        print('MESSAGE RECEIVED:')
        print(message)
    def on_data(ws, message, data_type, continue_bool):
        print('DATA RECEIVED:')
        print(message)
    def on_error(ws, error):
        print('ERROR:')
        print(error)
    def on_open(ws):
        print('*******  OPEN  *******')
    def on_close(ws):
        print('******* CLOSED *******')

    try:
        url = ('wss://api.stockfighter.io/ob/api/ws/{}/venues/{}/tickertape/stocks/{}'
               .format(account, venue, stock))
        websocket.enableTrace(True)
        ws = websocket.WebSocketApp(url,
                                    on_open=on_open, on_message=on_message,
                                    on_error=on_error, on_close=on_close,
                                    on_data=on_data)
        ws.run_forever()
    except KeyboardInterrupt:
        pass


def test_fills1():
    url = ('wss://api.stockfighter.io/ob/api/ws/{}/venues/{}/executions'
               .format(account, venue, stock))
    ws = websocket.create_connection(url)
    print('****** OPENED *******')
    res = ws.recv()
    print('RECEIVED: {}'.format(res))
    print('****** CLOSING *******')
    ws.close()

