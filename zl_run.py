from hw10_data_orig import (
    MATERIAL, CAPACITY, CUSTOMER, NO_LATE, TIME,
    usage, sub_usage, ord_cost, ord_qty,
    demand, baseprice, supply,
    init_funds, min_buy, max_buy, friday, p_disc
)
from hw10_data_conversion import data_to_op
from hw10_model import Hw9_model


OPERATIONS, BOP, BOR, usage_param, produce_param, offset_param, MAT2, CAP2 = data_to_op(
    set(MATERIAL),          
    set(CAPACITY),
    CUSTOMER,
    NO_LATE,
    TIME,
    usage,
    sub_usage,
    ord_cost,
    ord_qty,
    demand,
    baseprice,
    supply
)

solver = Hw9_model(
    MAT2,          
    CAP2,          
    CUSTOMER,
    TIME,
    usage,
    sub_usage,
    demand,
    supply,
    init_funds,
    min_buy,
    max_buy,
    friday,
    OPERATIONS,
    BOR,
    BOP,
    usage_param,
    produce_param,
    offset_param,
    baseprice,
    p_disc,
    mult={},          
    scrap_pen={},     
    stoc_pen={},
    make_pen={}
)

print("Solve finished.")
