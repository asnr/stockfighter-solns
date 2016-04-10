from __future__ import print_function

import time

from lib import *

venue = 'BPEMEX'
stock = 'EMHI'
account = 'MB84763092'

purse = StockPurse(venue, stock, account)

def simple_market_maker(stock_purse, num_rounds, lag, qty_per_round,
                        qty_tolerance, delta=100):

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

        bid_price = adjusted_mid_point - (delta // 2)
        ask_price = bid_price + delta

        print('Best ask price: {:>5}, best bid price: {:5}, midpoint: {:5}'
              .format(best_ask_price, best_bid_price, price_mid_point))
        print('Adjusted mid point: {:>5}  (stocks held: {})'
              .format(adjusted_mid_point, stocks_held))
        print('')

        # Send bid order
        print(('Bidding price:{price:>6}, qty:{qty:>5}...'
                .format(qty=qty_per_round, price=bid_price)), end='')
        try:
            buy_resp = stock_purse.buy('limit', qty=qty_per_round,
                                       price=bid_price)
        except OrderError as e:
            buy_resp = None
            print(' FAILED {}'.format(print_order_err(e)))
        else:
            print(' 200 OK')
            print_fills(buy_resp['fills'])
            

        # Send ask order
        print(('Asking price:{price:>6}, qty:{qty:>5}...'
                .format(qty=qty_per_round, price=ask_price)), end='')
        try:
            sell_resp = stock_purse.sell('limit', qty=qty_per_round,
                                         price=ask_price)
        except OrderError as e:
            sell_resp = None
            print(' FAILED {}'.format(print_order_err(e)))
        else:
            print(' 200 OK')
            print_fills(sell_resp['fills'])

        time.sleep(lag)

        cancelled_orders = stock_purse.cancel_all()

        print('\nCurrent state: {:>5} stocks held, {:>9} basis'
              .format(stock_purse.stocks_held(), stock_purse.basis()))


def get_probe_quote(stock_purse, max_retries=10):
    probe_quote = None
    for attempt in range(max_retries):
        print('Issue probing quote...', end='')
        try:
            probe_quote = stock_purse.quote()
        except OrderError as e:
            print(' {}'.format(print_order_err(e)))
        else:
            print(' 200 OK, last price: {}'.format(probe_quote['last']))
            if 'ask' not in probe_quote or 'bid' not in probe_quote:
                probe_quote = None
                continue
            else:
                break

    return probe_quote


def print_order_err(e):
    if e.error_msg is None:
        print('status code: {}'.format(e.status_code))
    else:
        print('status code: {}, message {}'
              .format(e.status_code, e.error_msg))

def print_fills(fills):
    if len(fills) == 0:
        print('  received 0 fills.')
    elif len(fills) <= 3:
        print('  received {} fills:'.format(len(fills)))
    else:
        print('  top 3 of {} fills:'.format(len(fills)))
    for fill in fills[:3]:
        print('    price:{price:>9}, qty:{qty:>9}'
                .format(price=fill['price'], qty=fill['qty']))


def rolling_orderbook(secs_between_updates, num_orders_visible):
    def print_order(order):
        print('  Price:{price:>10}, Qty:{qty:>10}'
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
                print('  No asks :(')
            else:
                map(print_order, r_json['asks'][:num_orders_visible])
            
            print('                ...')
            
            if r_json['bids'] is None:
                print('  No bids :(')
            else:
                map(print_order, r_json['bids'][:num_orders_visible])

            time.sleep(secs_between_updates)        
    except KeyboardInterrupt:
        pass


# def simple_round_buyer(num_rounds, qty_per_round, secs_between_rounds):
#     min_qty_bought = 0

#     for round in range(num_rounds):
#         print('')
#         print('######## Round {} ########'.format(round + 1))
        
#         print('Issue probing quote...', end='')
#         probe_quote_resp = quote(venue, stock)
#         print(' status_code: ' + str(probe_quote_resp.status_code))
        
#         probe_quote = probe_quote_resp.json()
#         if 'bid' not in probe_quote:
#             print('ERROR, could not find key \'bid\'')
#             print(str(probe_quote))
#             continue

#         price = probe_quote['bid'] + 10
#         print('Bidding qty {} at {}...'.format(str(qty_per_round), str(price)),
#               end='')
#         r = buy(venue, stock, account, 'limit', qty=qty_per_round, price=price)
#         print(' status code: {}'.format(r.status_code))
#         print(r.text)
#         r_json = r.json()
#         min_qty_bought += r_json['totalFilled']
#         print('MIN QTY PURCHASED ' + str(min_qty_bought))
        
#         time.sleep(secs_between_rounds)

#         if r_json['qty'] > 0:
#             print('Cancelling order ' + str(r_json['id']) + '... ', end = '')
#             del_resp = delete(venue, stock, r_json['id'])
#             print('... status code: ' + str(del_resp.status_code))

