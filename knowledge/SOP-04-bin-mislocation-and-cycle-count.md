# SOP-04 Warehouse bin mislocation
When a putaway is confirmed manually (bin_confirmed = N) the item may sit in a neighbouring bin. Signature: one bin is overstated and a neighbouring bin of the same SKU is understated by the same quantity, the net is zero, and short picks appear at the system bin.
Action: create a targeted bin search task for the neighbouring bins first, then a bin transfer correction. No stock is lost.
