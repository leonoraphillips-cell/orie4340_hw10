# ORIE 5340 – HW10 Model Extension  
### Group Members  
- **Zhenming Li** (zl2277@cornell.edu)  
- **Leonora Phillips** (lkp42@cornell.edu)  
- **Jackson Douglas** (jhd86@cornell.edu)  
- **Jackson Carlberg** (jwc277@cornell.edu)  

---

## Overview

This project extends the HW8/HW9 operations-planning model to support **two production locations** (Doug's Garage and Janey's Studio), introduce **box inventory**, **transportation delays**, **quilt-top substitutions**, and **bundle-related operations**. The model is fully implemented in Python using OR-Tools’ linear solver.

The deliverables include:
1. Updated data definitions (`hw10_data_orig.py`)
2. A conversion script that constructs the model input (`hw10_data_conversion.py`)
3. The full model implementation (`hw10_model.py`)
4. A final run script (`run_hw10.py`)
5. A report summarizing results and model adjustments

---

## Key Assumptions Implemented

### Location & Transportation
- **All transfers between Doug and Janey incur a 1-day offset** (e.g., material sent on Dec 3 becomes usable at the destination on Dec 4).
- **Optional fixed-charge trip costs** (`Trip_D2J`, `Trip_J2D`) may be added but are set to zero in the final baseline.
- Production and shipping constraints:
  - **Janey only sews** (tops, beds, pillows, bags).
  - **All outbound shipping uses Doug's box inventory.**

### Box Inventory
- Boxes stored only at Doug’s Garage.
- Two box types introduced:
  - **SmallBox_D** → \$50 per order of 20  
  - **LargeBox_D** → \$75 per order of 20  
- Each shipped product requires exactly **one box**.

### Resource Cloning
To handle two locations, the model **clones all materials and intermediate products** that may appear at both sites:
- `_D` suffix → Doug  
- `_J` suffix → Janey  

Examples:
- `Fleece_D`, `Fleece_J`
- `Mesh_D`, `Mesh_J`
- `SFleeceTop_D`, `SFleeceTop_J`, etc.

### Bundles & Quilt Tops
- **FabricBundle_J** introduced for Janey; an unpack operation produces fleece/mesh/casing.
- **Quilted tops** (`QTopS_D`, `QTopM_D`, `QTopL_D`) purchased from a seamstress with **2-day delivery delay**.
- Beds may use either standard tops or quilted tops (substitution allowed).

### New Operations Added
- Full set of **_J operations** for Janey's production.
- **Transport operations** between locations for every cloned material.
- **Bundle unpacking operations**.
- **Box purchasing operations**.
- **Spoiled Dog Bundle** production and shipping.

---

## File Structure
