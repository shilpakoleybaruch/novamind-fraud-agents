# Journey: analyst resolves case (fraud_confirmed)

Case CASE-A2EDAC4B67, txn L-TXN-004

- PASS hold exists and is active before resolve 
- PASS resolve call accepted HTTP 200
- PASS case status resolved with resolved_at 
- PASS hold stays active (payment stays blocked) 
- PASS audit trail has case_resolved 
- FAIL Dana's page shows the final outcome no question row for txn
