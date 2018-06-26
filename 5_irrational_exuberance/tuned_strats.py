# With qty=60, price goes up by ~400 every round
slow_buyer(purse, target_position=-80, qty=60, price_delta=70, wait_before_cancel=4, wait_after_cancel=6)

decrease_maker(purse, target_price=4000, crash_price_delta=400, crash_qty=150, resting_qty=300, min_position=-3000, crash_lag=2, max_rounds=4)
