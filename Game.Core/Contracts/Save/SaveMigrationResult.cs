namespace Game.Core.Contracts.Save;

/// <summary>
/// Result of applying a save schema migration decision.
/// </summary>
public readonly record struct SaveMigrationResult(bool Succeeded, string? ErrorMessage)
{
    public static SaveMigrationResult Success()
    {
        return new SaveMigrationResult(true, null);
    }

    public static SaveMigrationResult Failure(string errorMessage)
    {
        return new SaveMigrationResult(false, errorMessage);
    }
}
