from __future__ import print_function

from lib import *

venue = 'NLYYEX'
stock = 'IIQH'
account = 'KAT63487981'

def simple_round_buyer(num_rounds, qty_each_round, secs_between_rounds):
    min_qty_bought = 0

    for round in range(num_rounds):
        print('')
        print('######## Round {} ########'.format(round + 1))
        
        print('Issue probing quote...', end='')
        probe_quote_resp = quote(venue, stock)
        print(' status_code: ' + str(probe_quote_resp.status_code))
        
        probe_quote = probe_quote_resp.json()
        if 'bid' not in probe_quote:
            print('ERROR, could not find key \'bid\'')
            print(str(probe_quote))
            continue

        price = probe_quote['bid'] + 10
        print('Bidding qty {} at {}...'.format(str(qty_each_round), str(price)),
              end='')
        r = buy(venue, stock, account, 'limit', qty=qty_each_round, price=price)
        print(' status code: {}'.format(r.status_code))
        print(r.text)
        r_json = r.json()
        min_qty_bought += r_json['totalFilled']
        print('MIN QTY PURCHASED ' + str(min_qty_bought))
        
        time.sleep(secs_between_rounds)

        if r_json['qty'] > 0:
            print('Cancelling order ' + str(r_json['id']) + '... ', end = '')
            del_resp = delete(venue, stock, r_json['id'])
            print('... status code: ' + str(del_resp.status_code))



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
