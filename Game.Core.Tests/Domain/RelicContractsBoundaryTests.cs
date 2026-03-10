using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.RegularExpressions;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Domain;

public class RelicContractsBoundaryTests
{
    // ACC:T30.4
    [Fact]
    public void ShouldExposeRequiredMembers_WhenRelicDefinitionContractExists()
    {
        var relicDefinitionType = FindTypeByName("RelicDefinition");

        relicDefinitionType.Should().NotBeNull("RelicDefinition contract must exist in Game.Core.Contracts");

        var members = GetPublicFieldAndPropertyNames(relicDefinitionType!).ToHashSet(StringComparer.OrdinalIgnoreCase);

        members.Should().BeEquivalentTo(new[] { "relic_id", "name_key", "description_key", "tags" });
    }

    // ACC:T30.5
    [Fact]
    public void ShouldExposeRequiredMembers_WhenRelicInstanceContractExists()
    {
        var relicInstanceType = FindTypeByName("RelicInstance");

        relicInstanceType.Should().NotBeNull("RelicInstance contract must exist in Game.Core.Contracts");

        var members = GetPublicFieldAndPropertyNames(relicInstanceType!).ToHashSet(StringComparer.OrdinalIgnoreCase);

        members.Should().BeEquivalentTo(new[] { "instance_id", "modifiers" });
    }

    // ACC:T30.6
    [Fact]
    public void ShouldKeepRelicContractsOnlyInContractsNamespace_WhenScanningAssembly()
    {
        var root = FindRepositoryRoot();
        var sourceFiles = Directory
            .EnumerateFiles(root, "*.cs", SearchOption.AllDirectories)
            .Where(path => !path.Contains("\\bin\\", StringComparison.OrdinalIgnoreCase))
            .Where(path => !path.Contains("\\obj\\", StringComparison.OrdinalIgnoreCase))
            .Where(path => !path.Contains("\\.godot\\", StringComparison.OrdinalIgnoreCase))
            .ToArray();

        var declarationPattern = new Regex(
            @"\b(?:public|internal)?\s*(?:sealed\s+)?(?:partial\s+)?(?:record(?:\s+class)?|class)\s+(RelicDefinition|RelicInstance)\b",
            RegexOptions.Compiled);

        var declarations = sourceFiles
            .Select(path => new
            {
                Path = NormalizePath(path, root),
                Matches = declarationPattern.Matches(File.ReadAllText(path))
            })
            .Where(x => x.Matches.Count > 0)
            .SelectMany(x => x.Matches.Cast<Match>().Select(m => new { x.Path, TypeName = m.Groups[1].Value }))
            .ToList();

        declarations.Should().NotBeEmpty();
        declarations
            .Where(x => x.Path.StartsWith("Game.Core/Contracts/", StringComparison.OrdinalIgnoreCase))
            .Select(x => x.TypeName)
            .Distinct(StringComparer.Ordinal)
            .Should()
            .Contain(new[] { "RelicDefinition", "RelicInstance" });

        declarations
            .Where(x => !x.Path.StartsWith("Game.Core/Contracts/", StringComparison.OrdinalIgnoreCase))
            .Should()
            .BeEmpty("contract declarations must exist only under Game.Core/Contracts");
    }

    private static IEnumerable<string> GetPublicFieldAndPropertyNames(Type type)
    {
        var propertyNames = type
            .GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Select(p => p.Name);

        var fieldNames = type
            .GetFields(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Select(f => f.Name);

        return propertyNames.Concat(fieldNames);
    }

    private static bool IsInContractsNamespace(string? typeNamespace)
    {
        return !string.IsNullOrWhiteSpace(typeNamespace)
            && typeNamespace!.StartsWith("Game.Core.Contracts", StringComparison.Ordinal);
    }

    private static string FindRepositoryRoot()
    {
        var dir = new DirectoryInfo(Path.GetDirectoryName(GetCurrentSourceFilePath())!);
        while (dir is not null)
        {
            var marker = Path.Combine(dir.FullName, "project.godot");
            if (File.Exists(marker))
            {
                return dir.FullName;
            }

            dir = dir.Parent;
        }

        throw new DirectoryNotFoundException("Could not locate repository root from current source file.");
    }

    private static string NormalizePath(string absolutePath, string root)
    {
        var relative = Path.GetRelativePath(root, absolutePath);
        return relative.Replace('\\', '/');
    }

    private static string GetCurrentSourceFilePath([CallerFilePath] string path = "") => path;

    private static Type? FindTypeByName(string typeName)
    {
        return FindAllTypesByName(typeName).FirstOrDefault();
    }

    private static IEnumerable<Type> FindAllTypesByName(string typeName)
    {
        return GetCandidateAssemblies()
            .SelectMany(GetLoadableTypes)
            .Where(t => string.Equals(t.Name, typeName, StringComparison.Ordinal));
    }

    private static IEnumerable<Assembly> GetCandidateAssemblies()
    {
        var loaded = AppDomain.CurrentDomain.GetAssemblies().ToList();
        var coreAssembly = loaded.FirstOrDefault(a => string.Equals(a.GetName().Name, "Game.Core", StringComparison.Ordinal));

        if (coreAssembly is null)
        {
            try
            {
                coreAssembly = Assembly.Load("Game.Core");
            }
            catch
            {
                coreAssembly = null;
            }
        }

        return coreAssembly is null ? loaded : loaded.Append(coreAssembly).Distinct();
    }

    private static IEnumerable<Type> GetLoadableTypes(Assembly assembly)
    {
        try
        {
            return assembly.GetTypes();
        }
        catch (ReflectionTypeLoadException ex)
        {
            return ex.Types.Where(t => t is not null)!;
        }
    }
}
