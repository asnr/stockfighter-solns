from __future__ import print_function

import time

from ws4py.client.threadedclient import WebSocketClient
import json

from lib import *

# stu hunter - Migration Suite

account = 'AAW40171639'
venue = 'YDIXEX'
stock = 'VUYC'

init_stocks_held = 0
init_basis = 0
purse = StockPurse(venue, stock, account, stocks_held=init_stocks_held, basis=init_basis)


def shy_maker(stock_purse, num_rounds=30, wait_secs=4, qty_tolerance=400,
              tolerance_adjust=1000, qty_marks=(1000, 2000, 10000, 30000, 50000),
              price_delta_fallback=400, qtys=(100, 200, 200, 200, 100),
              informed_qty=10000, informed_penalty=400, dont_stop=True):
    '''Every round, get orderbook and make orders with prices based on quantities
    in the orderbook vs. `qty_marks` argument. For example, at qty_mark=(50,),
    one sell order will be issued that round at the price you need to buy the
    first 50 stocks on the last orderbook retrieved, and a similar buy order
    will be also be placed. If the absolute number of stocks held goes above by
    a multiple n of `qty_tolerance`, the prices for the next orders in that
    direction will be moved n*`tolerance_adjust` in that direction.

    In addition, if any order on the orderbook has quantity > `informed_qty`,
    then fall back to the last prices, but spread by an extra
    `informed_penalty`'''

    last_uninformed_ask_prices = []
    last_uninformed_bid_prices = []
    for round in range(num_rounds):
        print('')
        print('######## Round {} ########'.format(round + 1))

        probe_book = get_probe_orderbook(stock_purse, max_retries=10, pause=0.6)
        if probe_book is None:
            print('Couldn\'t get a probe orderbook!', end='')
            if dont_stop:
                continue
            else:
                print(' Exiting...')
                return

        print('')

        if any_informed_orders(probe_book, threshold=informed_qty):
            #informed_orders = get_informed_orders(probe_book, threshold=informed_qty)
            ask_prices = [p + informed_penalty
                          for p in last_uninformed_ask_prices]
            bid_prices = [max(p - informed_penalty, 0)
                          for p in last_uninformed_bid_prices]
        else:
            ask_prices = price_till_qty(probe_book['asks'], qty_marks,
                                        price_delta_fallback, are_bids=False)
            bid_prices = price_till_qty(probe_book['bids'], qty_marks,
                                        price_delta_fallback, are_bids=True)
            last_uninformed_ask_prices = ask_prices
            last_uninformed_bid_prices = bid_prices

        stocks_held = stock_purse.stocks_held()
        # Note price_adjust always positive
        price_adjust = (abs(stocks_held) // qty_tolerance) * tolerance_adjust
        if stocks_held < -qty_tolerance:
            ask_prices = [price + price_adjust for price in ask_prices]
        elif stocks_held > qty_tolerance:
            bid_prices = [max(price - price_adjust, 0) for price in bid_prices]

        # Eliminate orders that will put us over the risk quantity limit if
        # filled
        ask_prices = ask_prices[:idx_cumsum_gt(qtys, 999 + stocks_held)]
        bid_prices = bid_prices[:idx_cumsum_gt(qtys, 999 - stocks_held)]

        # Send bid orders, lowest first so that the printout is easier to read
        buy_ids = []
        for price, qty in reversed(zip(bid_prices, qtys)):
            print(('Bidding price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                buy_resp = stock_purse.buy('limit', qty=qty, price=price)
            except APIResponseError as e:
                buy_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                buy_ids.append(buy_resp['id'])
                print(' OK, filled {} stocks, ID {}'
                      .format(buy_resp['totalFilled'], buy_resp['id']))

        # Send ask orders
        sell_ids = []
        for price, qty in zip(ask_prices, qtys):
            print(('Asking price: {price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                sell_resp = stock_purse.sell('limit', qty=qty, price=price)
            except APIResponseError as e:
                sell_resp = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                sell_ids.append(sell_resp['id'])
                print(' OK, filled {} stocks, ID {}'
                      .format(sell_resp['totalFilled'], sell_resp['id']))

        time.sleep(wait_secs)

        cancelled_orders = stock_purse.cancel_all()

        qty_bought = sum(stock_purse.qty_filled(id) for id in buy_ids)
        qty_sold = sum(stock_purse.qty_filled(id) for id in sell_ids)

        print('\nAt round end, sold qty: {}, bought qty: {},\n              stocks held: {}, basis: {}, NAV: {}.'
              .format(qty_sold, qty_bought, stock_purse.stocks_held(),
                      stock_purse.basis(), stock_purse.value()))


def any_informed_orders(orderbook, threshold):
    informed_asks = (ask['qty'] > threshold for ask in orderbook['asks'])
    informed_bids = (bid['qty'] > threshold for bid in orderbook['bids'])
    return any(informed_asks) or any(informed_bids)


def idx_cumsum_gt(values, threshold):
    cumsum = 0
    for idx, val in enumerate(values):
        cumsum += val
        if cumsum > threshold:
            return idx

    return len(values)


# def asymmetric_maker(stock_purse, num_rounds=30, wait_secs=2, qty_tolerance=350,
#                      tolerance_adjust=1000, qty_marks=(20, 100, 400),
#                      price_delta_fallback=100, qtys=(20, 100, 100)):
#     '''Every round, get orderbook and make orders with prices based on quantities
#     in the orderbook vs. `qty_marks` argument. For example, at qty_mark=(50,),
#     one sell order will be issued that round at the price you need to buy the
#     first 50 stocks on the last orderbook retrieved, and a similar buy order
#     will be also be placed. If the absolute number of stocks held goes above by
#     a multiple n of `qty_tolerance`, the prices for the next orders in that
#     direction will be moved n*`tolerance_adjust` in that direction.'''

#     for round in range(num_rounds):
#         print('')
#         print('######## Round {} ########'.format(round + 1))

#         probe_book = get_probe_orderbook(stock_purse)
#         if probe_book is None:
#             print('Couldn\'t get a probe orderbook! Exiting...')
#             return

#         print('')

#         ask_prices = price_till_qty(probe_book['asks'], qty_marks,
#                                     price_delta_fallback, are_bids=False)
#         bid_prices = price_till_qty(probe_book['bids'], qty_marks,
#                                     price_delta_fallback, are_bids=True)

#         stocks_held = stock_purse.stocks_held()
#         # Note price_adjust always positive
#         price_adjust = (abs(stocks_held) // qty_tolerance) * tolerance_adjust
#         if stocks_held < -qty_tolerance:
#             ask_prices = [price + price_adjust for price in ask_prices]
#         elif stocks_held > qty_tolerance:
#             bid_prices = [max(price - price_adjust, 0) for price in bid_prices]

#         # Send bid orders
#         buy_ids = []
#         for price, qty in zip(bid_prices, qtys):
#             print(('Bidding price:{price:>6}, qty:{qty:>5}...'
#                     .format(qty=qty, price=price)), end='')
#             try:
#                 buy_resp = stock_purse.buy('limit', qty=qty, price=price)
#             except APIResponseError as e:
#                 buy_resp = None
#                 print(' FAILED {}'.format(print_order_err(e)))
#             else:
#                 buy_ids.append(buy_resp['id'])
#                 print(' 200 OK, filled {} stocks, ID {}'
#                       .format(buy_resp['totalFilled'], buy_resp['id']))

#         # Send ask orders
#         sell_ids = []
#         for price, qty in zip(ask_prices, qtys):
#             print(('Asking price:{price:>6}, qty:{qty:>5}...'
#                     .format(qty=qty, price=price)), end='')
#             try:
#                 sell_resp = stock_purse.sell('limit', qty=qty, price=price)
#             except APIResponseError as e:
#                 sell_resp = None
#                 print(' FAILED {}'.format(print_order_err(e)))
#             else:
#                 sell_ids.append(sell_resp['id'])
#                 print(' 200 OK, filled {} stocks, ID {}'
#                       .format(sell_resp['totalFilled'], sell_resp['id']))

#         time.sleep(wait_secs)

#         cancelled_orders = stock_purse.cancel_all()

#         qty_bought = sum(stock_purse.qty_filled(id) for id in buy_ids)
#         qty_sold = sum(stock_purse.qty_filled(id) for id in sell_ids)

#         print('\nAt round end, sold qty: {}, bought qty: {},\n              stocks held: {}, basis: {}, NAV: {}.'
#               .format(qty_sold, qty_bought, stock_purse.stocks_held(),
#                       stock_purse.basis(), stock_purse.value()))


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


def get_probe_quote(stock_purse, max_retries=10):
    probe_quote = None
    for attempt in range(max_retries):
        print('Issue probing quote...', end='')
        try:
            probe_quote = stock_purse.quote()
        except APIResponseError as e:
            print(' {}'.format(print_order_err(e)))
        else:
            print(' OK, last price: {}'.format(probe_quote['last']))
            if 'ask' not in probe_quote or 'bid' not in probe_quote:
                probe_quote = None
                continue
            else:
                break

    return probe_quote


def get_probe_orderbook(stock_purse, max_retries=10, pause=None):
    probe_orderbook = None
    for attempt in range(max_retries):
        if attempt != 0 and pause is not None:
            time.sleep(pause)

        print('GET orderbook...', end='')
        try:
            probe_orderbook = stock_purse.orderbook()
        except APIResponseError as e:
            print(' {}'.format(print_order_err(e)))
        else:
            asks = probe_orderbook['asks']
            bids = probe_orderbook['bids']
            print(' OK, number bids: {}, asks: {}'
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
              .format(e.status_code, e.error_msg.strip()))

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
            j = json.loads(m)
            pretty_j = None
            if not j['ok']:
                pretty_j = j
            else:
                pretty_j['standingID'] = j['standingID']
                pretty_j['incomingID'] = j['incomingID']
                pretty_j['filledAt'] = j['filledAt']
                pretty_j['standingComplete'] = j['standingComplete']
                pretty_j['incomingComplete'] = j['incomingComplete']
                pretty_j['order'] = j['order']
            print(json.dumps(pretty_j, indent = 4, separators=(',', ': ')))
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

