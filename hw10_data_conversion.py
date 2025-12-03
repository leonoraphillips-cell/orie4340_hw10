from collections import defaultdict




def data_to_op(MATERIAL, CAPACITY, CUSTOMER, NO_LATE, TIME,
              usage, sub_usage, ord_cost, ord_qty, demand, baseprice, supply):


   # modified so that MATERIAL isn't mutated (for solve time)
   base_mats = list(MATERIAL)
   for MAT in base_mats:
       if MAT in {'Money', 'JaneyTime', 'DougTime', 'PickupTime', 'DeliverTime'}:
           continue
       studio_mat = f"{MAT}_Studio"
       MATERIAL.add(studio_mat)


   MATERIAL.add('Money')


   CAPACITY |= {'PickupTime', 'DeliverTime', 'Transport_G2S', 'Transport_S2G'}


   # We must pre-calculate HAS_DEMAND here
   HAS_DEMAND = set()
   for c in CUSTOMER:
       for r in MATERIAL:
           if any(demand.get((r, c), [0] * len(TIME))[i] > 0 for i in range(len(TIME))):
               HAS_DEMAND.add((c, r))


   for (c, r) in HAS_DEMAND:
       demand_res = f"D_{c}_{r}"  # e.g., "D_Store_P"
       if c in NO_LATE:
           CAPACITY.add(demand_res)  # No late shipments allowed
       else:
           MATERIAL.add(demand_res)  # Can be "stocked" (backlogged)


   OPERATIONS = set()
   BOR = set()  # set of (op, res)
   BOP = set()  # set of (op, res)
   usage_param = defaultdict(float)  # usage[(op,res)]
   produce_param = defaultdict(float)  # produce[(op,res)]
   offset_param = defaultdict(int)  # offset[(op,res)]


   # Big-M for PickupTime and DeliverTime: one trip can handle all demand
   total_demand = 0
   for (item, cust), dem_list in demand.items():
       total_demand += sum(dem_list)
   BIGM_TRIP = max(1, total_demand)


   # Conversion Operations
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


   # MAKE Op
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


   #  SUBSTITUTION
   for (p, r, q_sub) in sub_usage.keys():
       k_sub = f"Make_{p}_with_{q_sub}"
       OPERATIONS.add(k_sub)


       base_inputs = by_item.get(p, [])


       # Is this a Janey-time (studio) operation?
       is_janey_op = (q_sub == 'JaneyTime')


       for (res, q) in base_inputs:
           if res == r:
               continue
           if q > 0:
               eff_res = res
               # If Janey is doing this at the studio, use studio copies
               if is_janey_op and res not in {'DougTime', 'JaneyTime', 'Money',
                                              'PickupTime', 'DeliverTime'}:
             eff_res = f"{res}_Studio"
               BOR.add((k_sub, eff_res))
               usage_param[(k_sub, eff_res)] = q


       # JaneyTime or DougTime capacity
       BOR.add((k_sub, q_sub))
       usage_param[(k_sub, q_sub)] = sub_usage[(p, r, q_sub)]


       # Product is always the "garage" product (bed top, pillow, bag)
       BOP.add((k_sub, p))
       produce_param[(k_sub, p)] = 1.0


       # If the base make-op produced some byproduct, copy it over
       for (res, q) in base_inputs:
           if q < 0:
               BOP.add((k_sub, res))
               produce_param[(k_sub, res)] = abs(q)


   # BUY Op
   for r, cost in ord_cost.items():
       if r not in ord_qty:
           continue
       k = f"Buy_{r}"
       OPERATIONS.add(k)
       BOR.add((k, "Money"))


       if r == 'FabricBundle':
           # special buy bundle, it shows up as fabric at STUDIO same day
           usage_param[(k, "Money")] += float(cost)  # 200 from data_orig


           # explode bundle into studio fabrics
           BOP.add((k, 'Fleece_Studio'))
           produce_param[(k, 'Fleece_Studio')] += 30*36


           BOP.add((k, 'Mesh_Studio'))
           produce_param[(k, 'Mesh_Studio')] += 30 * 36


           BOP.add((k, 'Casing_Studio'))
           produce_param[(k, 'Casing_Studio')] += 200 * 36


           # no PickupTime cost, no offset: arrives same period at studio
           continue


       # standard buy behavior for everything else (garage)
       usage_param[(k, "Money")] += float(cost)
       BOP.add((k, r))
       produce_param[(k, r)] += float(ord_qty[r])


       if r not in {'JaneyTime', 'DougTime'}:
           BOR.add((k, "PickupTime"))
           usage_param[(k, "PickupTime")] += 1.0


   # NEW: Buy Boxes
   # Assuming cost/qty bc we forgot to ask on ED
   # We assume Doug can buy them individually for now, we can modify later with new info
   box_types = ['SmallBox', 'LargeBox']
   for box in box_types:
       k = f"Buy_{box}"
       OPERATIONS.add(k)
       BOR.add((k, "Money"))
       usage_param[(k, "Money")] += 0.75  # assuming price of boxes as we forgot to ask
       BOP.add((k, box))
       produce_param[(k, box)] += 1.0


       # Boxes need to be picked up
       BOR.add((k, "PickupTime"))
       usage_param[(k, "PickupTime")] += 1.0


       MATERIAL.add(box)  # Ensures it's in MATERIAL


   # SHIP Op
   def ship_name(item, cust):
       return f"Ship_{cust}_{item}"


   for (cust, item) in HAS_DEMAND:
       price = float(baseprice.get((item, cust), 0.0))


       # We must create a ship op even if price is 0, to consume the demand
       k = ship_name(item, cust)
       OPERATIONS.add(k)


       # Check if customer is Online. Large items must use large box
       # everything else fits in a small
       if cust == 'Online':
           if ('Large' in item and 'Bed' in item) or 'Bundle' in item:
               BOR.add((k, 'LargeBox'))
               usage_param[(k, 'LargeBox')] += 1.0
           else:
               BOR.add((k, 'SmallBox'))
               usage_param[(k, 'SmallBox')] += 1.0


       # consume the item
       BOR.add((k, item))
       usage_param[(k, item)] += 1.0


       # not sure if online consumes DeliverTime, but we assume it does
       # bc he prob needs to go to post office
       # if not online, we can uncomment and move the next two line inside
       # if cust != 'Online':
       BOR.add((k, "DeliverTime"))
       usage_param[(k, "DeliverTime")] += 1.0


       # consume the Demand Resource
       demand_res = f"D_{cust}_{item}"
       BOR.add((k, demand_res))
       usage_param[(k, demand_res)] += 1.0


       # produce Money (use the BASE price)
       BOP.add((k, "Money"))
       produce_param[(k, "Money")] += price


       # not sure if only store gets the offset, if so
       # uncomment the line below and move inside loop
       # if cust == 'Store':
       offset_param[(k, "Money")] = 1


   # MOVE ops for Garage to/from Studio
   # We approximate the fixed-trip costs $30 (Doug2Janey) and $50 (Janey2Doug)


   # Create "Courier Trip" Operations (The Fixed Cost)
   # Trip G->S ($30 fixed cost, creates infinite capacity)
  
   # we set a large enough capacity so that the courier is never full,
   # this results in large qty of scap for unused capacity, but it works :)
   BigM_Move = sum(supply.values())
  
   op_trip_d2j = "Op_Trip_Garage_to_Studio"
   OPERATIONS.add(op_trip_d2j)
   BOR.add((op_trip_d2j, 'Money'))
   usage_param[(op_trip_d2j, 'Money')] = 30.0
   BOP.add((op_trip_d2j, 'Transport_G2S'))
   produce_param[(op_trip_d2j, 'Transport_G2S')] = BigM_Move 


   # Trip S->G ($50 fixed cost, creates infinite capacity)
   op_trip_j2d = "Op_Trip_Studio_to_Garage"
   OPERATIONS.add(op_trip_j2d)
   BOR.add((op_trip_j2d, 'Money'))
   usage_param[(op_trip_j2d, 'Money')] = 50.0
   BOP.add((op_trip_j2d, 'Transport_S2G'))
   produce_param[(op_trip_j2d, 'Transport_S2G')] = BigM_Move


   # Doug (garage) to Janey (studio)
   for r in list(MATERIAL):
       # Skip special / non-physical resources
       if r in {'Money', 'JaneyTime', 'DougTime', 'PickupTime', 'DeliverTime'}:
           continue
       if r.startswith('D_'):
           continue       # never move demand resources
       if r.endswith('_Studio'):
           continue       # base resources only


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


       # Doug2Janey is "same day" so offset 0
       offset_param[(op_move, r_studio)] = 0


   # Janey (studio) to Doug (garage)
   for r in list(MATERIAL):
       if not r.endswith('_Studio'):
           continue
       base_r = r[:-7]  # strip "_Studio"


       # Again skip weird/special ones
       if base_r in {'Money', 'JaneyTime', 'DougTime',
                     'PickupTime', 'DeliverTime'}:
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


       # Janey2Doug is overnight so arrives next period
       offset_param[(op_move_back, base_r)] = 1


   # NEW: Seamstress Operations
   # Define costs mapping
   seamstress_costs = {'Small': 15.0, 'Medium': 25.0, 'Large': 35.0}


   for size, cost in seamstress_costs.items():
       top_name = f"QTop_{size}"  # e.g. QTop_Small
       MATERIAL.add(top_name)


       k = f"Buy_Seamstress_{size}"
       OPERATIONS.add(k)


       # Consumes Money immediately
       BOR.add((k, "Money"))
       usage_param[(k, "Money")] += cost


       # Produces Top 2 days later
       BOP.add((k, top_name))
       produce_param[(k, top_name)] += 1.0
       offset_param[(k, top_name)] = 2


   # Does NOT need PickupTime, we assume this is a delivery servive,
   # but can update accordingly


   return OPERATIONS, BOP, BOR, usage_param, produce_param, offset_param, MATERIAL, CAPACITY

