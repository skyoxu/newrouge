using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class CombatServiceDependencyTests
{
    private static readonly string[] UiDependencyTokens =
    {
        "Game.UI",
        "Game.Godot.UI",
        ".UI.",
        "Godot.",
    };

    private static readonly string[] PresentationBoundaryTokens =
    {
        "Game.UI",
        "Game.Godot.UI",
        "Godot.",
        "System.Text.Json",
    };

    // ACC:T11.13
    // ACC:T11.17
    [Fact]
    public void ShouldNotDependOnUiLayerTypes_WhenInspectingCombatServicePublicAndPrivateSurface()
    {
        var typeNames = CollectTypeNamesFromCombatServiceSurface();
        var violations = FindTokenViolations(typeNames, UiDependencyTokens);

        violations.Should().BeEmpty("CombatService must stay independent from UI layer types.");
    }

    [Fact]
    public void ShouldDetectUiLayerDependency_WhenForbiddenTypeTokenAppearsInSignatureList()
    {
        var typeNames = new[]
        {
            "Game.Core.Contracts.Interfaces.IEventBus",
            "Game.UI.HudCombatWidget",
            "System.String",
        };

        var violations = FindTokenViolations(typeNames, UiDependencyTokens);

        violations.Should().ContainSingle();
        violations[0].Should().Contain("Game.UI.HudCombatWidget");
    }

    // ACC:T11.16
    // ACC:T11.18
    [Fact]
    public void ShouldKeepCombatServiceFreeFromPresentationBoundaryLeaks_WhenScanningSourceTokens()
    {
        var sourcePath = Path.Combine(FindRepoRoot(), "Game.Core", "Services", "CombatService.cs");
        File.Exists(sourcePath).Should().BeTrue("CombatService source file must exist for dependency boundary checks.");

        var source = File.ReadAllText(sourcePath);
        var violations = FindTokenViolations(new[] { source }, PresentationBoundaryTokens);

        violations.Should().BeEmpty("core combat logic should not format presentation payloads or reference UI-facing stacks.");
    }

    private static List<string> CollectTypeNamesFromCombatServiceSurface()
    {
        var serviceType = typeof(CombatService);
        var collected = new HashSet<string>(StringComparer.Ordinal);

        foreach (var constructor in serviceType.GetConstructors(BindingFlags.Public | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        {
            foreach (var parameter in constructor.GetParameters())
            {
                AddTypeNameRecursive(parameter.ParameterType, collected);
            }
        }

        foreach (var method in serviceType.GetMethods(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly))
        {
            AddTypeNameRecursive(method.ReturnType, collected);
            foreach (var parameter in method.GetParameters())
            {
                AddTypeNameRecursive(parameter.ParameterType, collected);
            }
        }

        foreach (var field in serviceType.GetFields(BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly))
        {
            AddTypeNameRecursive(field.FieldType, collected);
        }

        return collected.OrderBy(name => name, StringComparer.Ordinal).ToList();
    }

    private static void AddTypeNameRecursive(Type type, ISet<string> collected)
    {
        var fullName = type.FullName ?? type.Name;
        collected.Add(fullName);

        if (type.IsArray)
        {
            AddTypeNameRecursive(type.GetElementType()!, collected);
            return;
        }

        if (!type.IsGenericType)
        {
            return;
        }

        foreach (var argument in type.GetGenericArguments())
        {
            AddTypeNameRecursive(argument, collected);
        }
    }

    private static List<string> FindTokenViolations(IEnumerable<string> values, IEnumerable<string> forbiddenTokens)
    {
        var violations = new List<string>();
        var seenValues = new HashSet<string>(StringComparer.Ordinal);

        foreach (var value in values)
        {
            foreach (var token in forbiddenTokens)
            {
                if (value.Contains(token, StringComparison.Ordinal))
                {
                    if (seenValues.Add(value))
                    {
                        violations.Add($"{value} -> {token}");
                    }

                    break;
                }
            }
        }

        return violations;
    }

    private static string FindRepoRoot()
    {
        var current = new DirectoryInfo(AppContext.BaseDirectory);

        while (current is not null)
        {
            var marker = Path.Combine(current.FullName, ".taskmaster");
            if (Directory.Exists(marker))
            {
                return current.FullName;
            }

            current = current.Parent;
        }

        throw new DirectoryNotFoundException("Cannot locate repository root from test execution directory.");
    }
}
