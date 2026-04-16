using Game.Core.Contracts.Save;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Validates or migrates autosave schema before continue entry becomes available.
/// </summary>
public interface ISaveMigrationService
{
    SaveMigrationResult TryMigrate(string schemaVersion);
}
