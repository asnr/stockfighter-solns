from __future__ import print_function

import logging

import httplib
# There are only two debuglevel values: zero and positive
#httplib.HTTPConnection.debuglevel = 1

import time

from ws4py.client.threadedclient import WebSocketClient
import json

from lib import *

logging.basicConfig(
    format='%(asctime)s,%(msecs)d %(name)s %(levelname)s:%(message)s',
    datefmt='%H:%M:%S', level=logging.INFO, filename='logs')


account = 'LAS87930542'
venue = 'OZEX'
stock = 'IBS'

init_position = 0
init_basis = 0
purse = StockPurse(
    venue, stock, account, position=init_position, basis=init_basis)


def slow_buyer(stock_purse, target_position=-3000, qty=200, price_delta=75,
               wait_before_cancel=4, wait_after_cancel=5):
    """Try to sell lots of stock before crashing the price.

    To not crash the stock, sell `qty` at `price_delta` below top bid
    on orderbook. Wait `wait_before_cancel` seconds, then cancel, then wait
    `wait_after_cancel` seconds. Repeat.

    Once we hit `target_position`, stop."""

    round_num = 0
    while(target_position < stock_purse.position()):

        round_num += 1
        print('')
        print('###### Slow buy, round {} ######'.format(round_num))
        print('')

        probe_book = get_probe_orderbook(
            stock_purse, max_retries=10, pause=0.6, require_asks=False)

        ask_price = probe_book['bids'][0]['price'] - price_delta

        print(('\nAsking price:{price:>6}, qty:{qty:>5}...'
                   .format(qty=qty, price=ask_price)), end='')
        try:
            ask = stock_purse.sell(
                'limit', qty=qty, price=ask_price)
        except APIResponseError as e:
            print(' FAILED {}'.format(print_order_err(e)))
            break
        else:
            print(' OK')

        time.sleep(wait_before_cancel)

        stock_purse.cancel_all()

        qty_sold = stock_purse.qty_filled(ask.id)
        print('\nAt round end, sold qty: {}\n              stocks held: {}, basis: {}, NAV: {}.'
              .format(qty_sold, stock_purse.position(), stock_purse.basis(),
                      stock_purse.value()))

        time.sleep(wait_after_cancel)


def decrease_maker(stock_purse, target_price=2000, crash_price_delta=400,
                   crash_qty=250, resting_qty=500, min_position=-7000,
                   crash_lag=2, max_rounds=4):
    """Crash the market value of a stock by steadily decreasing ask
    prices. It appears that other traders will crash the price if
    several of their consecutive trades are filled at steadily lower
    prices. Consequently, once we start crashing the price, we must
    ensure that other traders *fill every order at a price equal to or
    less than their previous fill*.

    This strategy has rounds, at no point apart from the end are all
    outstanding orders cancelled at once, and the rounds should be
    relatively short. This is so that there is always an ask order
    resting on the book.

    It works as follows:
     1. Get the orderbook, first bid price on book is the starting ask price.
     2. Decrease the ask price by `crash_price_delta`.
     3. Ask `crash_qty`. Repeat until there is some amount is not
        filled, i.e. some of the order is left resting on the book.
     4. Ask `resting_qty`.
     5. Cancel old asks at price higher than the last ask (we want other
        traders to always fill at a price no more than their last fill).
     6. Wait `crash_lag` seconds.
     7. Go to 2.

    If we will either ask too far below `target_price` or if we are at
    risk of selling past the `min_position`, then stop selling and
    cancel all outstanding orders.
    """

    # Get latest bids--we'll start at the top bid
    probe_book = get_probe_orderbook(
        stock_purse, max_retries=12, pause=0.6, require_asks=False)

    if probe_book is None:
        print('Couldn\'t get a probe orderbook!', end='')
        return

    ask_price = probe_book['bids'][0]['price']

    round_num = 0
    min_pos_buffered = min_position + crash_qty + resting_qty + 1
    last_ask_ids = []
    # Note we may go one round at a price below `target_price`
    while (min_pos_buffered < stock_purse.position() and
           target_price < ask_price and round_num < max_rounds):
        
        round_num += 1
        print('')
        print('###### Crash the stock, round {} ######'.format(round_num))
        print('')

        ask_price -= crash_price_delta

        # Get some asks resting on the book at `ask_price`
        ask_ids = []
        qty_rested = 0
        while qty_rested == 0:

            if stock_purse.position_with_open_asks() - crash_qty < min_position:
                finish_strat(stock_purse)
                return

            print(('Asking price:{price:>6}, qty:{qty:>5}...'
                   .format(qty=crash_qty, price=ask_price)), end='')
            try:
                ask = stock_purse.sell(
                    'limit', qty=crash_qty, price=ask_price)
            except APIResponseError as e:
                print(' FAILED {}'.format(print_order_err(e)))
                break
            else:
                print(' OK, filled {} stocks, ID {}'
                  .format(ask.qty_filled(), ask.id))
            
            ask_ids.append(ask.id)
            
            qty_rested = ask.qty_resting()
        
        # Send the resting order
        if stock_purse.position_with_open_asks() - resting_qty < min_position:
            finish_strat(stock_purse)
            return

        print(('Asking price:{price:>6}, qty:{qty:>5}...'
                   .format(qty=resting_qty, price=ask_price)), end='')
        try:
            ask = stock_purse.sell(
                'limit', qty=resting_qty, price=ask_price)
        except APIResponseError as e:
            print(' FAILED {}'.format(print_order_err(e)))
        else:
            print(' OK, filled {} stocks, ID {}'
                  .format(ask.qty_filled(), ask.id))

        ask_ids.append(ask.id)

        for ask_id in last_ask_ids:
            stock_purse.cancel(ask_id)

        print('\nAt round end, stocks held: {}, basis: {}, NAV: {}.'
          .format(stock_purse.position(), stock_purse.basis(),
                  stock_purse.value()))

        time.sleep(crash_lag)

        last_ask_ids = ask_ids


    finish_strat(stock_purse)


def finish_strat(stock_purse):
    stock_purse.cancel_all()
    print('\nAt strat end, stocks held: {}, basis: {}, NAV: {}.'
          .format(stock_purse.position(), stock_purse.basis(),
                  stock_purse.value()))    


def crash_maker(stock_purse, target_price=2000, crash_price_delta=400,
                crash_qty=400, crash_rest_qty=1200, min_position=-9999,
                crash_lag=5):
    """Crash the market value of a stock by selling.

    One round of crashing works as follows:
      1. Get the orderbook, first bid price is ask price
      2. Ask `crash_qty`
      3. Note the qty rested. If any rested, reduce price by
         `crash_price_delta`. 
      3. Go to 2, unless total qty rested >=`crash_rest_qty` or we are at risk
         of hitting `min_position.
      5. Wait `crash_lag` seconds, cancel all orders and go to 1.

    If we have cannot place any more asks without sum of position and qty
    outstanding hitting `min_position` or when the price hits
    `target_price`, stop.
    """

    round_num = 0
    min_pos_buffered = min_position + crash_qty + 1
    ask_price = None
    while (min_pos_buffered < stock_purse.position() and
           (ask_price is None or target_price < ask_price)):

        round_num += 1
        print('')
        print('###### Crash the stock, round {} ######'.format(round_num))
        print('')

        # Get latest bids--we'll start at the top bid
        probe_book = get_probe_orderbook(
            stock_purse, max_retries=10, pause=0.6, require_asks=False)

        if probe_book is None:
            print('Couldn\'t get a probe orderbook!', end='')
            continue

        ask_ids = []
        ask_price = probe_book['bids'][0]['price'] - crash_price_delta
        qty_rested = 0
        while (qty_rested < crash_rest_qty and
               min_pos_buffered < stock_purse.position_with_open_asks() and
               target_price < ask_price):
            print(('Asking price:{price:>6}, qty:{qty:>5}...'
                   .format(qty=crash_qty, price=ask_price)), end='')
            try:
                ask = stock_purse.sell(
                    'limit', qty=crash_qty, price=ask_price)
            except APIResponseError as e:
                print(' FAILED {}'.format(print_order_err(e)))
                break
            
            ask_ids.append(ask.id)
            print(' OK, filled {} stocks, ID {}'
                  .format(ask.qty_filled(), ask.id))
            qty_rested += ask.qty_resting()
            if ask.is_open():
                ask_price -= crash_price_delta

        time.sleep(crash_lag)

        stock_purse.cancel_all()

        qty_sold = sum(stock_purse.qty_filled(id) for id in ask_ids)
        print('\nAt round end, sold qty: {}\n              stocks held: {}, basis: {}, NAV: {}.'
              .format(qty_sold, stock_purse.position(), stock_purse.basis(),
                      stock_purse.value()))



def shy_maker(stock_purse, num_rounds=30, wait_secs=4, qty_tolerance=2000,
              tolerance_adjust=400, qty_marks=(250, 500, 1000, 2500, 10000, 30000),
              price_delta_fallback=300, qtys=(50, 200, 200, 200, 300, 300),
              informed_qty=10000, informed_penalty=400):
    """Every round, get orderbook and make orders with prices based on quantities
    in the orderbook vs. `qty_marks` argument. For example, at qty_mark=(50,),
    one sell order will be issued that round at the price you need to buy the
    first 50 stocks on the last orderbook retrieved, and a similar buy order
    will be also be placed. If the absolute number of stocks held goes above by
    a multiple n of `qty_tolerance`, the prices for the next orders in that
    direction will be moved n*`tolerance_adjust` in that direction.

    In addition, if any order on the orderbook has quantity > `informed_qty`,
    then fall back to the last prices, but spread by an extra
    `informed_penalty`.
    """

    last_uninformed_ask_prices = []
    last_uninformed_bid_prices = []
    for round in range(num_rounds):
        print('')
        print('######## Round {} ########'.format(round + 1))

        probe_book = get_probe_orderbook(stock_purse, max_retries=10, pause=0.6)
        if probe_book is None:
            print('Couldn\'t get a probe orderbook!', end='')
            continue
            
        print('')

        if any_informed_orders(probe_book, threshold=informed_qty):
            #informed_orders = get_informed_orders(probe_book, threshold=informed_qty)
            ask_prices = [p + informed_penalty
                          for p in last_uninformed_ask_prices]
            bid_prices = [max(p - informed_penalty, 0)
                          for p in last_uninformed_bid_prices]
        else:
            ask_prices = price_till_qty(
                probe_book['asks'], qty_marks, price_delta_fallback,
                are_bids=False)
            bid_prices = price_till_qty(
                probe_book['bids'], qty_marks, price_delta_fallback,
                are_bids=True)

            last_uninformed_ask_prices = ask_prices
            last_uninformed_bid_prices = bid_prices

        position = stock_purse.position()
        # Note price_adjust always positive
        price_adjust = (abs(position) // qty_tolerance) * tolerance_adjust
        if position < -qty_tolerance:
            ask_prices = [price + price_adjust for price in ask_prices]
        elif position > qty_tolerance:
            bid_prices = [max(price - price_adjust, 0) for price in bid_prices]

        # Eliminate orders that will put us over the risk quantity limit if
        # filled
        ask_prices = ask_prices[:idx_cumsum_gt(qtys, 9999 + position)]
        bid_prices = bid_prices[:idx_cumsum_gt(qtys, 9999 - position)]

        # Send bid orders, lowest first so that the printout is easier to read
        buy_ids = []
        for price, qty in reversed(zip(bid_prices, qtys)):
            print(('Bidding price:{price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                bid = stock_purse.buy('limit', qty=qty, price=price)
            except APIResponseError as e:
                bid = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                buy_ids.append(bid.id)
                print(' OK, filled {} stocks, ID {}'
                      .format(bid.qty_filled(), bid.id))

        # Send ask orders
        sell_ids = []
        for price, qty in zip(ask_prices, qtys):
            print(('Asking price: {price:>6}, qty:{qty:>5}...'
                    .format(qty=qty, price=price)), end='')
            try:
                ask = stock_purse.sell('limit', qty=qty, price=price)
            except APIResponseError as e:
                ask = None
                print(' FAILED {}'.format(print_order_err(e)))
            else:
                sell_ids.append(ask.id)
                print(' OK, filled {} stocks, ID {}'
                      .format(ask.qty_filled(), ask.id))

        time.sleep(wait_secs)

        cancelled_orders = stock_purse.cancel_all()

        qty_bought = sum(stock_purse.qty_filled(id) for id in buy_ids)
        qty_sold = sum(stock_purse.qty_filled(id) for id in sell_ids)

        print('\nAt round end, sold qty: {}, bought qty: {},\n              stocks held: {}, basis: {}, NAV: {}.'
              .format(qty_sold, qty_bought, stock_purse.position(),
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


def price_till_qty(orders, qtys, price_delta_fallback, are_bids):
    """Return a list of prices."""

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


def get_probe_orderbook(stock_purse, max_retries=10, pause=None,
                        require_asks=True, require_bids=True):
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

            if require_asks:
                need_asks = asks is None or len(asks) == 0
            else:
                need_asks = False
            if require_bids:
                need_bids = bids is None or len(bids) == 0
            else:
                need_bids = False

            if need_asks or need_bids:
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

