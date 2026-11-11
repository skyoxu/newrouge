# Proposed clarified toy fixture — NOT sent or approved

For this test each reward has a stable reward_id. Reward acceptance completes when the durable RewardAccepted(reward_id) record exists. A return is the durable MapReturnCommitted(reward_id) transition; displaying the restored map after restart is not another transition.

Each accepted reward must cause exactly one MapReturnCommitted transition, during uninterrupted execution or the first resumed execution able to run the handoff, without another user action. A crash before reward acceptance owes no return. A crash after acceptance but before the return commit must resume the pending return. A crash after that commit must restore the map without committing a second return. These rules also hold across repeated restarts. Verify the durable records and transition count for each boundary.
