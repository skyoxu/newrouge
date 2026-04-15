using System.Collections;
using System.Collections.Generic;
using System.Reflection;
using Game.Core.Contracts.Interfaces;

namespace Game.Core.Services;

/// <summary>
/// Executes configured map acts in deterministic <c>act_id</c> order.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0021.
/// </remarks>
public sealed class MapActConfigurationService
{
    /// <summary>
    /// Validate and resolve all requested act configurations.
    /// </summary>
    /// <param name="requestedActCount">Requested count of acts to execute, starting from act 1.</param>
    /// <param name="provider">Act configuration provider.</param>
    /// <returns><see langword="true"/> when all requested acts are available; otherwise <see langword="false"/>.</returns>
    public bool TryRunConfiguredActs(int requestedActCount, IActConfigProvider provider)
    {
        if (requestedActCount <= 0 || provider is null)
        {
            return false;
        }

        if (TryResolveConfiguredActCount(provider, out var configuredActCount) && configuredActCount < requestedActCount)
        {
            return false;
        }

        for (var actId = 1; actId <= requestedActCount; actId++)
        {
            try
            {
                _ = provider.GetByActId(actId);
            }
            catch (KeyNotFoundException)
            {
                return false;
            }
            catch (ArgumentException)
            {
                return false;
            }
            catch (InvalidOperationException)
            {
                return false;
            }
        }

        return true;
    }

    private static bool TryResolveConfiguredActCount(IActConfigProvider provider, out int configuredActCount)
    {
        configuredActCount = 0;
        var binding = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var providerType = provider.GetType();

        foreach (var property in providerType.GetProperties(binding))
        {
            if (property.GetIndexParameters().Length > 0 || property.GetMethod is null)
            {
                continue;
            }

            if (property.PropertyType == typeof(int) && IsCountLikeMember(property.Name))
            {
                var value = property.GetValue(provider);
                if (value is int intValue && intValue > 0)
                {
                    configuredActCount = intValue;
                    return true;
                }
            }

            if (TryExtractCollectionCount(property.Name, property.GetValue(provider), out configuredActCount))
            {
                return true;
            }
        }

        foreach (var field in providerType.GetFields(binding))
        {
            if (field.FieldType == typeof(int) && IsCountLikeMember(field.Name))
            {
                var value = field.GetValue(provider);
                if (value is int intValue && intValue > 0)
                {
                    configuredActCount = intValue;
                    return true;
                }
            }

            if (TryExtractCollectionCount(field.Name, field.GetValue(provider), out configuredActCount))
            {
                return true;
            }
        }

        return false;
    }

    private static bool TryExtractCollectionCount(string memberName, object? value, out int count)
    {
        count = 0;
        if (!IsConfigLikeMember(memberName) || value is null)
        {
            return false;
        }

        if (value is ICollection collection)
        {
            count = collection.Count;
            return count > 0;
        }

        return false;
    }

    private static bool IsCountLikeMember(string memberName)
    {
        return memberName.Contains("count", StringComparison.OrdinalIgnoreCase) &&
               (memberName.Contains("act", StringComparison.OrdinalIgnoreCase) ||
                memberName.Contains("config", StringComparison.OrdinalIgnoreCase));
    }

    private static bool IsConfigLikeMember(string memberName)
    {
        return memberName.Contains("config", StringComparison.OrdinalIgnoreCase) ||
               memberName.Contains("act", StringComparison.OrdinalIgnoreCase);
    }
}
