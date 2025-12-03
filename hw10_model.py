# hw9 model


from ortools.linear_solver import pywraplp
from collections import defaultdict


# helper method
def prev(TIME, t, n=1):
   """
       Helper method to select an element from an ordered set.
       :param TIME: Ordered set
       :param t: index of current element
       :param n: shift steps
       :return: element at requested position
       """
   if TIME.index(t) - n < 0:
       return None  # Return None if index is out of bounds
   return TIME[TIME.index(t) - n]


def Hw9_model(MATERIAL, CAPACITY, CUSTOMER, TIME,
             usage, sub_usage, demand, supply,
             init_funds, min_buy, max_buy, friday,
             # NEW HW8 PARAMETERS
             OPERATIONS,
             BOR, BOP, usage_param, produce_param, offset_param,
             baseprice, p_disc, mult={},


             scrap_pen={}, stoc_pen={}, make_pen={}):
   """Multiple Level Multiple Product Resource Allocation Model with substitution,Procurement
    and multiple demands (store, online), and different source of labor modeled as Operations"""


   # Solver
   # Create the mip solver with the SCIP backend.
   solver = pywraplp.Solver.CreateSolver('gurobi')
   infinity = solver.infinity()


   # Set
   # MATERIAL now includes 'Money' from the data file
   RESOURCE = MATERIAL.union(CAPACITY)


   # These are only used for the make_pen objective
   BOM = set(usage.keys())
   PROD = {p for (p, r) in BOM}
   SUB_TRIPLES = set(sub_usage.keys())


   # BigM is only needed for min_buy
   BigM = 1e9
   alpha = .5


   # Param Default values
   min_buy = defaultdict(lambda: 1, min_buy)
   supply = defaultdict(lambda: 0, supply)
   supply[('Money', TIME[0])] = init_funds
   demand = defaultdict(lambda: [0] * len(TIME), demand)
   mult = defaultdict(lambda: 1, mult)
   sub_pen = defaultdict(lambda: 2 * alpha)
   scrap_pen = defaultdict(lambda: alpha, scrap_pen)
   stoc_pen = defaultdict(lambda: .5 * alpha, stoc_pen)
   make_pen = defaultdict(lambda: alpha, make_pen)




   # adding demand as supply
   for c in CUSTOMER:
       for r in MATERIAL:
           if any(demand.get((r, c), [0] * len(TIME))[i] > 0 for i in range(len(TIME))):
               demand_res = f"D_{c}_{r}"
               for t in TIME:
                   t_index = TIME.index(t)
                   period_demand = demand.get((r, c), [0] * len(TIME))[t_index]
                   if period_demand > 0:
                       supply[(demand_res, t)] = period_demand


   # Mapping resource-level min buys to operation-level min buys
   min_buy_ops = {f"Buy_{r}": v for r, v in min_buy.items()}
   HAS_MIN_OPS = {op for op in OPERATIONS if min_buy_ops.get(op, 1) > 1}


   # for r in RESOURCE:
   #     if r.startswith('D_'):
   #         scrap_pen[r] =BigM




   # Variables
   Scrap = {}
   Stock = {}
   # Ship and Shortfall removed; no longer needed
   z = {}


  # keeping scrap and stock as variables since hw assignment only
   # requires Make, Buy, Ship, and it's easier to keep as is
   for t in TIME:
       for r in RESOURCE:
           Scrap[t, r] = solver.NumVar(0.0, infinity, f'Scrap[{t, r}]')
   for t in TIME:
       for r in MATERIAL:
           Stock[t, r] = solver.NumVar(0.0, infinity, f'Stock[{t, r}]')


   # Operation Variable
   BinOp = {}
   for t in TIME:
       for op in OPERATIONS:
           if (op == 'Op_Make_PickupTime' or op == 'Op_Make_DeliverTime'or
                   op.startswith('Op_Trip_')):
               z[t, op] = solver.BoolVar(f'z[{t, op}]')
           elif op.startswith('Buy_JaneyTime'):
               ub = infinity
               if 'JaneyTime' in max_buy:
                   mb = max_buy['JaneyTime']
                   if isinstance(mb, dict):
                       if t in mb:
                           ub = mb[t]
                   else:  # in case data given as list instead
                       ub = mb[TIME.index(t)]
               z[t, op] = solver.IntVar(0, ub, f'z[{t, op}]')


           elif op.startswith('Buy_DougTime'):
               ub = infinity
               if 'DougTime' in max_buy:
                   mb = max_buy['DougTime']
                   if isinstance(mb, dict):
                       if t in mb:
                           ub = mb[t]
                   else:
                       ub = mb[TIME.index(t)]
               z[t, op] = solver.IntVar(0, ub, f'z[{t, op}]')
           else:
               z[t, op] = solver.IntVar(0, infinity, f'z[{t, op}]')


           if op in HAS_MIN_OPS:
               BinOp[t, op] = solver.BoolVar(f'BinOp[{t, op}]')


   # Objective
   objective_terms = []


   for r in MATERIAL.difference(PROD):
       if r == 'Money':
           continue
       for t in TIME:
           objective_terms.append(-1 * scrap_pen[r] * Scrap[t, r])
   for r in MATERIAL:
       if r == 'Money':
           continue
       for t in TIME:
           objective_terms.append(-1 * stoc_pen[r] * Stock[t, r])


   # Objective terms for Make Operations
   for t in TIME:
       for p in PROD:
           op_name = f"Make_{p}"
           if op_name in OPERATIONS and (t, op_name) in z:
               objective_terms.append(-1 * make_pen[p] * z[t, op_name])


           for (p_sub, r_sub, q_sub) in SUB_TRIPLES:
               if p_sub == p:
                 op_sub_name = f"Make_{p}_with_{q_sub}"
                   if op_sub_name in OPERATIONS and (t, op_sub_name) in z:
                       objective_terms.append(-1 * sub_pen[r_sub] * z[t, op_sub_name])


   # Constraints
   # Main model constraint: Resource balance for time periods
   for t in TIME:
       for r in RESOURCE:
           sources_from_ops = []
           for op in OPERATIONS:
               op_produces_r = (op, r) in BOP
               if op_produces_r:
                   prev_t = prev(TIME, t, offset_param.get((op, r), 0))
                   if prev_t is not None and (prev_t, op) in z:
                       sources_from_ops.append(
                           z[prev_t, op] * produce_param.get((op, r), 0))
           solver.Add((Stock[t, r] if r in MATERIAL else 0) +
                      (Scrap[t, r] if r in RESOURCE.difference(PROD) else 0) +
                      solver.Sum(z[t, op] * usage_param.get((op, r), 0)
                                 for op in OPERATIONS if (t, op) in z and (op, r) in BOR)
                      == supply.get((r, t), 0) + (Stock[prev(TIME, t, 1), r] if
                                                  (r in MATERIAL and TIME.index(t) > 0) else 0) +
                      solver.Sum(sources_from_ops),
                      name=f'R_Balance[{t, r}]')


   # to force min nonzero operation quantities
   for t in TIME:
       for op in HAS_MIN_OPS:
           if (t, op) in z and (t, op) in BinOp:
               solver.Add(BigM * BinOp[t, op] >= z[t, op], name=f'ForceBinOp[{t, op}]')
               solver.Add(z[t, op] >= BinOp[t, op] * min_buy_ops[op], name=f'ForceMinOp[{t, op}]')


   # "Either/Or" Schedule Constraint
   op_pickup = 'Op_Make_PickupTime'
   op_deliver = 'Op_Make_DeliverTime'
   if friday in TIME and op_pickup in OPERATIONS and op_deliver in OPERATIONS:
       for t in TIME:
           if t != friday:
               if (t, op_pickup) in z and (t, op_deliver) in z:
                   solver.Add(z[t, op_pickup] + z[t, op_deliver] <= 1,
                              name=f'Doug_EitherOr[{t}]')


   # Limit Scrap
   for r in MATERIAL.difference(PROD):
       if r == 'Money' or r.startswith('D_'):
           continue
       # This constraint is likely OK, but may be redundant with scrap penalties.
       solver.Add(solver.Sum([Scrap[t, r] for t in TIME]) <= supply.get((r, TIME[0]), 0),
                  name=f'LimitScrap[{r}')


   # terminal Money from revenue that arrives after the time horizon
   terminal_money_terms = []
   last_idx = len(TIME) - 1


   for t in TIME:
       t_idx = TIME.index(t)
       for op in OPERATIONS:
           if (op, 'Money') in BOP:
               arrive_idx = t_idx + offset_param.get((op, 'Money'), 0)
               # If Money would appear after the last modeled period,
               # we can't spend it, but we still want it in the objective.
               if arrive_idx > last_idx:
                   terminal_money_terms.append(
                       produce_param[(op, 'Money')] * z[t, op])


   # this part implements price discounting
 discount_terms = []
   for t in TIME:
       t_idx = TIME.index(t)
       disc_factor = (1.0 - p_disc) ** t_idx
       for op in OPERATIONS:
           if not op.startswith("Ship_"):
               continue
           if (t, op) not in z:
               continue
           _, cust, item = op.split("_", 2)
           base_nominal = baseprice[(item, cust)]
           base_discounted = mult[cust] * base_nominal * disc_factor
           diff = base_discounted - base_nominal
           discount_terms.append(diff * z[t, op])


   # setting the obj
   final_profit = Stock[TIME[-1], 'Money'] + solver.Sum(terminal_money_terms)


   solver.Maximize(final_profit +
                   solver.Sum(objective_terms)+
                   solver.Sum(discount_terms))


   # Solve
   solver.set_time_limit(150000)  # 150 seconds
   gap = 0.01
   solverParams = pywraplp.MPSolverParameters()
   solverParams.SetDoubleParam(solverParams.RELATIVE_MIP_GAP, gap)
   status = solver.Solve(solverParams)
  
  


   # Print solution.
   if status == pywraplp.Solver.OPTIMAL or status == pywraplp.Solver.FEASIBLE:
       print('Objective = {:.2f}\n'.format(solver.Objective().Value()))


       # Total Revenue (discounted)
       total_revenue = 0.0
       for (t, op), var in z.items():
           if not op.startswith("Ship_"):
               continue


           qty = var.solution_value()
           if qty <= 1e-6:
               continue


           # op = "Ship_<Cust>_<Item-with-underscores>"
           _, cust, item = op.split("_", 2)


           base_price = baseprice.get((item, cust), 0.0)
           t_idx = TIME.index(t)
           disc_factor = (1.0 - p_disc) ** t_idx


           total_revenue += qty * mult[cust] * base_price * disc_factor




       # Total Spending (Money going out)
       total_spend = 0.0
       for (t, op), var in z.items():
           qty = var.solution_value()
           if qty <= 1e-6:
               continue


           if (op, 'Money') in BOR:
               cost_per_unit = usage_param[(op, 'Money')]
               total_spend += qty * cost_per_unit


 accounting_profit = total_revenue - total_spend


       final_money = Stock[TIME[-1], 'Money'].solution_value()
       print(f"Final Money         = {final_money:.2f}")
       print(f"Total Revenue       = {total_revenue:.2f}")
       print(f"Total Spending      = {total_spend:.2f}")
       print(f"Actual Profit       = {accounting_profit:.2f}\n")


       # pretty print (more readable/presentable)
       print('\n*** Operation Variables (z) ***')


       # Helper to classify operation type for nicer grouping
       def classify_op(op_name: str) -> str:
           if op_name.startswith('Op_'):
               return 'Binary / Schedule Ops'
           elif op_name.startswith('Make_'):
               return 'Make Operations'
           elif op_name.startswith('Move_'):
               return 'Move Operations'
           elif op_name.startswith('Buy_'):
               return 'Buy Operations'
           elif op_name.startswith('Ship_'):
               return 'Ship Operations'
           else:
               return 'Other Operations'
       category_order = [
           'Binary / Schedule Ops',
           'Buy Operations',
           'Move Operations',
           'Make Operations',
           'Ship Operations',
           'Other Operations',
       ]


       # Desired print order of categories


       # Build a nested dict: day -> category -> list of (op, value)
       ops_by_day = {t: {cat: [] for cat in category_order} for t in TIME}


       for (t, op), var in z.items():
           val = var.solution_value()
           if val <= 0.1:
               continue  # skip essentially-zero ops
           cat = classify_op(op)
           if cat not in ops_by_day[t]:
               ops_by_day[t][cat] = []
           ops_by_day[t][cat].append((op, val))


       # Custom sort key for Move ops: G2S first, then S2G, then others
       def move_sort_key(op_val):
           op, _ = op_val
           if '_Garage_to_Studio' in op:
               dir_rank = 0
           elif '_Studio_to_Garage' in op:
               dir_rank = 1
           else:
               dir_rank = 2
           return (dir_rank, op)


       # Pretty print grouped operations
       for t in TIME:
           day_has_ops = any(ops_by_day[t][cat] for cat in category_order)
           if not day_has_ops:
               continue


           print(f'\n--- {t} ---')
           for cat in category_order:
               ops_list = ops_by_day[t][cat]
               if not ops_list:
                   continue


               print(f'  {cat}:')


               if cat == 'Move Operations':
                   sorted_ops = sorted(ops_list, key=move_sort_key)
               else:
                   sorted_ops = sorted(ops_list, key=lambda x: x[0])


               for op, val in sorted_ops:
                   print(f'    {op}: {val:.2f}')




       print('\nAdvanced usage:')
       print('Problem solved in ', solver.wall_time(), ' milliseconds')
       print('Problem solved in ', solver.iterations(), ' iterations')
   else:
       print('No solution found.')
   return solver


