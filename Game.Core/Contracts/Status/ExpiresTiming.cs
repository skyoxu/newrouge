namespace Game.Core.Contracts.Status;

/// <summary>
/// Timing at which status duration is consumed.
/// </summary>
public enum ExpiresTiming
{
    OwnerEndOfTurnCleanup = 1,
    OwnerStartOfTurn = 2,
    Never = 3,
}

