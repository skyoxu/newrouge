using Game.Core.Contracts.Interfaces;
using Game.Core.Contracts.Save;

namespace Game.Core.Services;

/// <summary>
/// Core continue gate behavior: continue is blocked until save migration succeeds.
/// </summary>
public sealed class ContinueGateService
{
    private readonly ISaveMigrationService migrationService;

    public ContinueGateService(ISaveMigrationService migrationService)
    {
        this.migrationService = migrationService;
    }

    public ContinueGateDecision Evaluate(AutosaveSnapshot snapshot)
    {
        var migrationResult = migrationService.AssessSchema(snapshot.SchemaVersion);
        if (migrationResult.Succeeded)
        {
            return new ContinueGateDecision(
                ContinueAvailable: true,
                EnterGameAllowed: true,
                ErrorMessage: null,
                StateAdvanced: true);
        }

        return new ContinueGateDecision(
            ContinueAvailable: false,
            EnterGameAllowed: false,
            ErrorMessage: migrationResult.ErrorMessage,
            StateAdvanced: false);
    }
}
