from collections import defaultdict

def data_to_op(MATERIAL, CAPACITY, CUSTOMER, NO_LATE, TIME,
               usage, sub_usage, ord_cost, ord_qty, demand, baseprice, supply):
    """
    Build operations data (OPERATIONS, BOR/BOP, usage/produce/offset) from original data.
    Implements:
      - Doug & Janey with cloned _Studio materials
      - All transfers Doug<->Janey have 1-period lead time
      - Trip_D2J / Trip_J2D with fixed per-trip costs
      - Box inventory only at Doug: SmallBox_D / LargeBox_D, with given costs & quantities
      - Every shipped product uses exactly 1 box
      - FabricBundle_Studio: Buy bundle then unpack into Fleece_Studio / Mesh_Studio / Casing_Studio
      - Seamstress quilt tops with 2-day delay
    """

    # 1) Clone studio materials (location split)
    base_mats = list(MATERIAL)
    for MAT in base_mats:
        if MAT in {'Money', 'JaneyTime', 'DougTime', 'PickupTime', 'DeliverTime'}:
            continue
        studio_mat = f"{MAT}_Studio"
        MATERIAL.add(studio_mat)

    MATERIAL.add('Money')

    # Transport capacities for trips
    CAPACITY |= {'PickupTime', 'DeliverTime', 'Transport_G2S', 'Transport_S2G'}

    # 2) Demand resources
    HAS_DEMAND = set()
    for c in CUSTOMER:
        for r in MATERIAL:
            if any(demand.get((r, c), [0] * len(TIME))[i] > 0 for i in range(len(TIME))):
                HAS_DEMAND.add((c, r))

    for (c, r) in HAS_DEMAND:
        demand_res = f"D_{c}_{r}"
        if c in NO_LATE:
            CAPACITY.add(demand_res)  # no-late demand as capacity
        else:
            MATERIAL.add(demand_res)  # backorderable demand as material

    OPERATIONS = set()
    BOR = set()   # (op, res) consumed
    BOP = set()   # (op, res) produced
    usage_param = defaultdict(float)
    produce_param = defaultdict(float)
    offset_param = defaultdict(int)

    # Big-M for PickupTime/DeliverTime productions
    total_demand = 0
    for (item, cust), dem_list in demand.items():
        total_demand += sum(dem_list)
    BIGM_TRIP = max(1, total_demand)

    # 3) DougTime -> PickupTime / DeliverTime
    op_pickup = "Op_Make_PickupTime"
    OPERATIONS.add(op_pickup)
    BOR.add((op_pickup, 'DougTime'))
    usage_param[(op_pickup, 'DougTime')] = 120.0
    BOP.add((op_pickup, 'PickupTime'))
    produce_param[(op_pickup, 'PickupTime')] = BIGM_TRIP

    op_deliver = "Op_Make_DeliverTime"
    OPERATIONS.add(op_deliver)
    BOR.add((op_deliver, 'DougTime'))
    usage_param[(op_deliver, 'DougTime')] = 120.0
    BOP.add((op_deliver, 'DeliverTime'))
    produce_param[(op_deliver, 'DeliverTime')] = BIGM_TRIP

    # 4) Base MAKE operations: Make_item
    by_item = defaultdict(list)
    for (item, res), q in usage.items():
        by_item[item].append((res, q))

    for item, rows in by_item.items():
        k = f"Make_{item}"
        OPERATIONS.add(k)
        for res, q in rows:
            if q > 0:
                BOR.add((k, res))
                usage_param[(k, res)] += q
            elif q < 0:
                BOP.add((k, res))
                produce_param[(k, res)] += abs(q)
        BOP.add((k, item))
        produce_param[(k, item)] += 1.0

    # 5) SUBSTITUTION-based MAKE ops (JaneyTime, etc.)
    for (p, r, q_sub) in sub_usage.keys():
        k_sub = f"Make_{p}_with_{q_sub}"
        OPERATIONS.add(k_sub)

        base_inputs = by_item.get(p, [])

        # JaneyTime operations consume _Studio versions of non-time resources
        is_janey_op = (q_sub == 'JaneyTime')

        for (res, q) in base_inputs:
            if res == r:
                continue
            if q > 0:
                eff_res = res
                if is_janey_op and res not in {'DougTime', 'JaneyTime', 'Money',
                                               'PickupTime', 'DeliverTime'}:
                    eff_res = f"{res}_Studio"
                BOR.add((k_sub, eff_res))
                usage_param[(k_sub, eff_res)] = q

        BOR.add((k_sub, q_sub))
        usage_param[(k_sub, q_sub)] = sub_usage[(p, r, q_sub)]

        # Product stays as "garage" product (p)
        BOP.add((k_sub, p))
        produce_param[(k_sub, p)] = 1.0

        # Copy over any byproducts if present
        for (res, q) in base_inputs:
            if q < 0:
                BOP.add((k_sub, res))
                produce_param[(k_sub, res)] = abs(q)

    # 6) BUY operations (with FabricBundle special case changed)
    for r, cost in ord_cost.items():
        if r not in ord_qty:
            continue
        k = f"Buy_{r}"
        OPERATIONS.add(k)
        BOR.add((k, "Money"))

        if r == 'FabricBundle':
            # Buy bundle delivered directly to Janey (studio side)
            usage_param[(k, "Money")] += float(cost)
            bundle_res = 'FabricBundle_Studio'
            MATERIAL.add(bundle_res)
            BOP.add((k, bundle_res))
            produce_param[(k, bundle_res)] += float(ord_qty[r])
            # No PickupTime, no offset: direct delivery to Janey
            continue

        # Standard buy behavior at Doug
        usage_param[(k, "Money")] += float(cost)
        BOP.add((k, r))
        produce_param[(k, r)] += float(ord_qty[r])

        if r not in {'JaneyTime', 'DougTime'}:
            BOR.add((k, "PickupTime"))
            usage_param[(k, "PickupTime")] += 1.0

    # 7) Buy Boxes at Doug only: SmallBox_D / LargeBox_D
    # SmallBox_D: $50 for 20; LargeBox_D: $75 for 20
    box_types = ['SmallBox_D', 'LargeBox_D']
    for box in box_types:
        k = f"Buy_{box}"
        OPERATIONS.add(k)
        BOR.add((k, "Money"))

        if box == 'SmallBox_D':
            usage_param[(k, "Money")] += 50.0
            qty = 20.0
        else:
            usage_param[(k, "Money")] += 75.0
            qty = 20.0

        BOP.add((k, box))
        produce_param[(k, box)] += qty

        BOR.add((k, "PickupTime"))
        usage_param[(k, "PickupTime")] += 1.0

        MATERIAL.add(box)  # box exists only at Doug; not cloned to _Studio

    # 8) SHIP operations: all shipments from Doug; each uses exactly 1 box
    def ship_name(item, cust):
        return f"Ship_{cust}_{item}"

    for (cust, item) in HAS_DEMAND:
        price = float(baseprice.get((item, cust), 0.0))

        k = ship_name(item, cust)
        OPERATIONS.add(k)

        # Large beds and bundles use a large box; everything else uses a small box
        if ('Large' in item and 'Bed' in item) or ('Bundle' in item):
            box_res = 'LargeBox_D'
        else:
            box_res = 'SmallBox_D'

        BOR.add((k, box_res))
        usage_param[(k, box_res)] += 1.0

        BOR.add((k, item))
        usage_param[(k, item)] += 1.0

        BOR.add((k, "DeliverTime"))
        usage_param[(k, "DeliverTime")] += 1.0

        demand_res = f"D_{cust}_{item}"
        BOR.add((k, demand_res))
        usage_param[(k, demand_res)] += 1.0

        BOP.add((k, "Money"))
        produce_param[(k, "Money")] += price
        offset_param[(k, "Money")] = 1  # 1-day delay for cash

    # 9) Trip fixed-cost operations Doug<->Janey
    BigM_Move = sum(supply.values())
    if BigM_Move <= 0:
        BigM_Move = 1.0

    op_trip_d2j = "Op_Trip_Garage_to_Studio"
    OPERATIONS.add(op_trip_d2j)
    BOR.add((op_trip_d2j, 'Money'))
    usage_param[(op_trip_d2j, 'Money')] = 30.0
    BOP.add((op_trip_d2j, 'Transport_G2S'))
    produce_param[(op_trip_d2j, 'Transport_G2S')] = BigM_Move

    op_trip_j2d = "Op_Trip_Studio_to_Garage"
    OPERATIONS.add(op_trip_j2d)
    BOR.add((op_trip_j2d, 'Money'))
    usage_param[(op_trip_j2d, 'Money')] = 50.0
    BOP.add((op_trip_j2d, 'Transport_S2G'))
    produce_param[(op_trip_j2d, 'Transport_S2G')] = BigM_Move

    # 10) Move Garage -> Studio: 1-period offset
    for r in list(MATERIAL):
        if r in {'Money', 'JaneyTime', 'DougTime', 'PickupTime', 'DeliverTime',
                 'Transport_G2S', 'Transport_S2G'}:
            continue
        if r.startswith('D_'):
            continue
        if r.endswith('_Studio'):
            continue

        r_studio = f"{r}_Studio"
        if r_studio not in MATERIAL:
            continue

        op_move = f"Move_{r}_Garage_to_Studio"
        OPERATIONS.add(op_move)

        BOR.add((op_move, r))
        usage_param[(op_move, r)] += 1.0

        BOR.add((op_move, "Transport_G2S"))
        usage_param[(op_move, "Transport_G2S")] += 1.0

        BOP.add((op_move, r_studio))
        produce_param[(op_move, r_studio)] += 1.0

        # Doug -> Janey: 1-period lead time
        offset_param[(op_move, r_studio)] = 1

    # 11) Move Studio -> Garage: 1-period offset
    for r in list(MATERIAL):
        if not r.endswith('_Studio'):
            continue
        base_r = r[:-7]

        if base_r in {'Money', 'JaneyTime', 'DougTime',
                      'PickupTime', 'DeliverTime',
                      'Transport_G2S', 'Transport_S2G'}:
            continue
        if base_r.startswith('D_'):
            continue

        op_move_back = f"Move_{base_r}_Studio_to_Garage"
        OPERATIONS.add(op_move_back)

        BOR.add((op_move_back, r))
        usage_param[(op_move_back, r)] += 1.0

        BOR.add((op_move_back, "Transport_S2G"))
        usage_param[(op_move_back, "Transport_S2G")] += 1.0

        BOP.add((op_move_back, base_r))
        produce_param[(op_move_back, base_r)] += 1.0

        # Janey -> Doug: 1-period lead time
        offset_param[(op_move_back, base_r)] = 1

    # 12) Unpack FabricBundle_Studio into Janey materials
    if 'FabricBundle_Studio' in MATERIAL:
        k = "Unpack_FabricBundle_Studio"
        OPERATIONS.add(k)

        BOR.add((k, 'FabricBundle_Studio'))
        usage_param[(k, 'FabricBundle_Studio')] += 1.0

        # 30y fleece + 30y mesh + 200y casing, converted to units (x36)
        BOP.add((k, 'Fleece_Studio'))
        produce_param[(k, 'Fleece_Studio')] += 30 * 36

        BOP.add((k, 'Mesh_Studio'))
        produce_param[(k, 'Mesh_Studio')] += 30 * 36

        BOP.add((k, 'Casing_Studio'))
        produce_param[(k, 'Casing_Studio')] += 200 * 36

    # 13) Seamstress quilt-top operations (2-day delay)
    seamstress_costs = {'Small': 15.0, 'Medium': 25.0, 'Large': 35.0}

    for size, cost in seamstress_costs.items():
        top_name = f"QTop_{size}"
        MATERIAL.add(top_name)

        k = f"Buy_Seamstress_{size}"
        OPERATIONS.add(k)

        BOR.add((k, "Money"))
        usage_param[(k, "Money")] += cost

        BOP.add((k, top_name))
        produce_param[(k, top_name)] += 1.0
        offset_param[(k, top_name)] = 2  # 2-day delay

    # Return structures in the original order
    return OPERATIONS, BOP, BOR, usage_param, produce_param, offset_param, MATERIAL, CAPACITY


