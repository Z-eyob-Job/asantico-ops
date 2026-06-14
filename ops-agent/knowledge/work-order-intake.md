# Work Order Intake

A new work order captures the property, the unit, the trade, and a description.
Each request is triaged into an urgency level and a trade.
Emergencies, such as an active leak, flooding, a gas smell, sparking, or no heat, are escalated to a human immediately.
Routine requests are queued for scheduling.
Urgency-based routing sends emergencies and ambiguous cases to the stronger model and routine cases to the faster model.
