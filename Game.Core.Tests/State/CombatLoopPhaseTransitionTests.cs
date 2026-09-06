using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts;
using Xunit;

namespace Game.Core.Tests.State;

public sealed class CombatLoopPhaseTransitionTests
{
    private static readonly IReadOnlyDictionary<string, string> CanonicalNext = new Dictionary<string, string>(StringComparer.Ordinal)
    {
        ["StartOfTurn"] = "Draw",
        ["Draw"] = "Main",
        ["Main"] = "EndOfTurn",
        ["EndOfTurn"] = "StartOfTurn",
    };

    public static IEnumerable<object[]> ValidTransitions()
    {
        yield return new object[] { "StartOfTurn", "Draw" };
        yield return new object[] { "Draw", "Main" };
        yield return new object[] { "Main", "EndOfTurn" };
        yield return new object[] { "EndOfTurn", "StartOfTurn" };
    }

    public static IEnumerable<object[]> InvalidTransitions()
    {
        yield return new object[] { "StartOfTurn", "Main" };
        yield return new object[] { "Draw", "EndOfTurn" };
        yield return new object[] { "Main", "StartOfTurn" };
        yield return new object[] { "EndOfTurn", "Draw" };
    }

    // ACC:T6.14
    [Theory]
    [MemberData(nameof(ValidTransitions))]
    public void ShouldAllowValidTransitions_WhenGuardIsSatisfied(string fromPhase, string toPhase)
    {
        var result = ProbeTransition(fromPhase, toPhase);

        result.GuardEvaluated.Should().BeTrue(result.Diagnostics);
        // RED-FIRST: this should fail until the combat loop transition contract is implemented.
        result.Allowed.Should().BeTrue($"Expected valid transition {fromPhase}->{toPhase}. {result.Diagnostics}");
        result.PhaseBefore.Should().Be(fromPhase);
        result.PhaseAfter.Should().Be(toPhase, $"Valid transition must advance state {fromPhase}->{toPhase}.");
        string.IsNullOrWhiteSpace(result.GuardMessage).Should().BeTrue("Valid transitions should not emit a guard rejection message.");
    }

    // ACC:T6.14
    [Theory]
    [MemberData(nameof(InvalidTransitions))]
    public void ShouldRejectInvalidTransitionsAndKeepStateUnchanged_WhenGuardFails(string fromPhase, string toPhase)
    {
        var result = ProbeTransition(fromPhase, toPhase);

        result.GuardEvaluated.Should().BeTrue(result.Diagnostics);
        result.Allowed.Should().BeFalse($"Expected invalid transition {fromPhase}->{toPhase} to be rejected. {result.Diagnostics}");
        result.PhaseBefore.Should().Be(fromPhase);
        result.PhaseAfter.Should().Be(fromPhase, "Rejected transition must keep phase unchanged.");
        result.GuardMessage.Should().NotBeNullOrWhiteSpace("Guard API should expose explicit rejection details.");
    }

    private static ProbeResult ProbeTransition(string fromPhase, string toPhase)
    {
        if (!TryResolveBinding(out var binding, out var resolveDiagnostics) || binding is null)
        {
            return new ProbeResult(false, false, null, null, null, resolveDiagnostics);
        }

        if (!TryCreateLoopAtPhase(binding, fromPhase, out var instance, out var setupDiagnostics) || instance is null)
        {
            return new ProbeResult(false, false, null, null, null, setupDiagnostics);
        }

        var before = ReadPhaseName(binding.CurrentPhaseProperty, instance);
        var transition = InvokeTransition(binding, instance, toPhase);
        var after = ReadPhaseName(binding.CurrentPhaseProperty, instance);

        return new ProbeResult(
            transition.GuardEvaluated,
            transition.Allowed,
            before,
            after,
            transition.GuardMessage,
            CombineDiagnostics(resolveDiagnostics, setupDiagnostics, transition.Diagnostics));
    }

    private static bool TryResolveBinding(out CombatLoopBinding? binding, out string diagnostics)
    {
        binding = null;
        diagnostics = "Combat loop contract not found.";

        var assembly = typeof(EventTypes).Assembly;

        var loopType = new[]
            {
                "Game.Core.Contracts.Combat.CombatLoop",
                "Game.Core.Contracts.CombatLoop",
                "Game.Core.Domain.Combat.CombatLoop",
                "Game.Core.Services.CombatLoop",
            }
            .Select(name => assembly.GetType(name, throwOnError: false, ignoreCase: false))
            .FirstOrDefault(type => type is not null)
            ?? SafeGetTypes(assembly).FirstOrDefault(type => type is not null && type.Name.Equals("CombatLoop", StringComparison.Ordinal));

        if (loopType is null)
        {
            return false;
        }

        var phaseProperty = loopType.GetProperty("CurrentPhase", BindingFlags.Public | BindingFlags.Instance)
            ?? loopType.GetProperty("Phase", BindingFlags.Public | BindingFlags.Instance)
            ?? loopType.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .FirstOrDefault(p => p.CanRead && p.PropertyType.Name.Contains("Phase", StringComparison.Ordinal));

        if (phaseProperty is null || !phaseProperty.CanRead)
        {
            diagnostics = $"Type {loopType.FullName} has no readable phase property.";
            return false;
        }

        var transitionMethod = loopType
            .GetMethods(BindingFlags.Public | BindingFlags.Instance)
            .Where(m => m.ReturnType != typeof(void))
            .Where(m => m.Name is "TryTransitionTo" or "TryTransition" or "TransitionTo" or "Transition" or "MoveToPhase")
            .Where(m =>
            {
                var p = m.GetParameters();
                if (p.Length is < 1 or > 2)
                {
                    return false;
                }

                var firstType = Nullable.GetUnderlyingType(p[0].ParameterType) ?? p[0].ParameterType;
                var firstSupported = firstType == phaseProperty.PropertyType || firstType == typeof(string);
                if (!firstSupported)
                {
                    return false;
                }

                if (p.Length == 2)
                {
                    return p[1].IsOut && p[1].ParameterType == typeof(string).MakeByRefType();
                }

                return true;
            })
            .OrderBy(m => m.GetParameters().Length)
            .ThenBy(m => m.Name, StringComparer.Ordinal)
            .FirstOrDefault();

        if (transitionMethod is null)
        {
            diagnostics = $"Type {loopType.FullName} has no supported transition method.";
            return false;
        }

        binding = new CombatLoopBinding(loopType, phaseProperty.PropertyType, phaseProperty, transitionMethod);
        diagnostics = $"Resolved {loopType.FullName}.{transitionMethod.Name}.";
        return true;
    }

    private static bool TryCreateLoopAtPhase(CombatLoopBinding binding, string phase, out object? instance, out string diagnostics)
    {
        instance = null;
        diagnostics = string.Empty;

        var ctors = binding.LoopType.GetConstructors(BindingFlags.Public | BindingFlags.Instance);

        var phaseCtor = ctors.FirstOrDefault(c =>
        {
            var p = c.GetParameters();
            if (p.Length != 1)
            {
                return false;
            }

            var t = Nullable.GetUnderlyingType(p[0].ParameterType) ?? p[0].ParameterType;
            return t == binding.PhaseType || t == typeof(string);
        });

        if (phaseCtor is not null)
        {
            var paramType = phaseCtor.GetParameters()[0].ParameterType;
            if (!TryConvertPhaseToken(paramType, phase, out var ctorValue))
            {
                diagnostics = $"Cannot convert phase token {phase}.";
                return false;
            }

            instance = phaseCtor.Invoke(new[] { ctorValue });
        }
        else
        {
            var defaultCtor = ctors.FirstOrDefault(c => c.GetParameters().Length == 0);
            if (defaultCtor is null)
            {
                diagnostics = $"Type {binding.LoopType.FullName} has no usable constructor.";
                return false;
            }

            instance = defaultCtor.Invoke(null);
        }

        var current = ReadPhaseName(binding.CurrentPhaseProperty, instance);
        if (string.Equals(current, phase, StringComparison.Ordinal))
        {
            diagnostics = "Initialized at requested phase.";
            return true;
        }

        if (binding.CurrentPhaseProperty.CanWrite && TryConvertPhaseToken(binding.CurrentPhaseProperty.PropertyType, phase, out var setValue))
        {
            binding.CurrentPhaseProperty.SetValue(instance, setValue);
            current = ReadPhaseName(binding.CurrentPhaseProperty, instance);
            if (string.Equals(current, phase, StringComparison.Ordinal))
            {
                diagnostics = "Phase set through writable property.";
                return true;
            }
        }

        if (string.IsNullOrWhiteSpace(current))
        {
            diagnostics = "Cannot resolve current phase for setup.";
            return false;
        }

        for (var i = 0; i < 8 && !string.Equals(current, phase, StringComparison.Ordinal); i++)
        {
            if (!CanonicalNext.TryGetValue(current, out var next))
            {
                diagnostics = $"No canonical setup path from {current} to {phase}.";
                return false;
            }

            var step = InvokeTransition(binding, instance, next);
            if (!step.GuardEvaluated || !step.Allowed)
            {
                diagnostics = CombineDiagnostics("Failed to advance during setup.", step.Diagnostics);
                return false;
            }

            current = ReadPhaseName(binding.CurrentPhaseProperty, instance);
            if (string.IsNullOrWhiteSpace(current))
            {
                diagnostics = "Phase became unavailable during setup.";
                return false;
            }
        }

        var success = string.Equals(current, phase, StringComparison.Ordinal);
        diagnostics = success ? "Reached requested setup phase." : $"Failed to reach requested phase {phase}.";
        return success;
    }

    private static TransitionResult InvokeTransition(CombatLoopBinding binding, object instance, string toPhase)
    {
        var parameters = binding.TransitionMethod.GetParameters();
        var args = new object?[parameters.Length];

        if (!TryConvertPhaseToken(parameters[0].ParameterType, toPhase, out var targetPhase))
        {
            return new TransitionResult(false, false, null, $"Cannot convert target phase token {toPhase}.");
        }

        args[0] = targetPhase;
        if (parameters.Length == 2)
        {
            args[1] = null;
        }

        object? returnValue;
        try
        {
            returnValue = binding.TransitionMethod.Invoke(instance, args);
        }
        catch (TargetInvocationException ex)
        {
            var baseEx = ex.InnerException ?? ex;
            return new TransitionResult(false, false, null, $"Transition threw {baseEx.GetType().Name}: {baseEx.Message}");
        }

        var hasAllowed =
            returnValue is bool ||
            TryReadBoolMember(returnValue, out _);

        if (!hasAllowed)
        {
            return new TransitionResult(false, false, null, "Transition result did not expose guard outcome.");
        }

        var allowed = returnValue is bool direct ? direct : TryReadBoolMember(returnValue, out var memberValue) && memberValue;
        var guardMessage = ExtractGuardMessage(instance, returnValue, args);

        return new TransitionResult(true, allowed, guardMessage, "Transition invoked.");
    }

    private static string? ExtractGuardMessage(object instance, object? returnValue, object?[] args)
    {
        if (args.Length == 2 && args[1] is string outGuard && !string.IsNullOrWhiteSpace(outGuard))
        {
            return outGuard;
        }

        if (TryReadStringMember(returnValue, out var fromResult))
        {
            return fromResult;
        }

        if (TryReadStringMember(instance, out var fromInstance))
        {
            return fromInstance;
        }

        return null;
    }

    private static bool TryReadBoolMember(object? source, out bool value)
    {
        value = false;
        if (source is null)
        {
            return false;
        }

        var type = source.GetType();
        foreach (var name in new[] { "Allowed", "IsAllowed", "CanTransition", "Success", "Succeeded" })
        {
            var property = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (property?.PropertyType == typeof(bool) && property.GetValue(source) is bool b)
            {
                value = b;
                return true;
            }
        }

        return false;
    }

    private static bool TryReadStringMember(object? source, out string? value)
    {
        value = null;
        if (source is null)
        {
            return false;
        }

        var type = source.GetType();
        foreach (var name in new[] { "GuardReason", "FailureReason", "Reason", "Error", "Message", "LastGuardFailureReason", "LastError" })
        {
            var property = type.GetProperty(name, BindingFlags.Public | BindingFlags.Instance);
            if (property?.PropertyType == typeof(string) && property.GetValue(source) is string text && !string.IsNullOrWhiteSpace(text))
            {
                value = text;
                return true;
            }
        }

        return false;
    }

    private static string? ReadPhaseName(PropertyInfo phaseProperty, object instance)
    {
        var value = phaseProperty.GetValue(instance);
        if (value is null)
        {
            return null;
        }

        if (value is string text)
        {
            return text;
        }

        var type = value.GetType();
        if (type.IsEnum)
        {
            return Enum.GetName(type, value) ?? value.ToString();
        }

        return value.ToString();
    }

    private static bool TryConvertPhaseToken(Type targetType, string phaseToken, out object? converted)
    {
        var normalized = Nullable.GetUnderlyingType(targetType) ?? targetType;

        if (normalized == typeof(string))
        {
            converted = phaseToken;
            return true;
        }

        if (normalized.IsEnum && Enum.TryParse(normalized, phaseToken, ignoreCase: true, out var parsed))
        {
            converted = parsed;
            return true;
        }

        converted = null;
        return false;
    }

    private static IEnumerable<Type> SafeGetTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException ex)
        {
            return ex.Types.Where(t => t is not null).Cast<Type>();
        }
    }

    private static string CombineDiagnostics(params string[] parts)
    {
        return string.Join(" | ", parts.Where(p => !string.IsNullOrWhiteSpace(p)));
    }

    private sealed record CombatLoopBinding(
        Type LoopType,
        Type PhaseType,
        PropertyInfo CurrentPhaseProperty,
        MethodInfo TransitionMethod);

    private sealed record TransitionResult(
        bool GuardEvaluated,
        bool Allowed,
        string? GuardMessage,
        string Diagnostics);

    private sealed record ProbeResult(
        bool GuardEvaluated,
        bool Allowed,
        string? PhaseBefore,
        string? PhaseAfter,
        string? GuardMessage,
        string Diagnostics);
}

