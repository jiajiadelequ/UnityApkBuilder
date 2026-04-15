using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;

public static class AndroidBuildTools
{
    const string DefaultOutputDir = "Builds/Android";
    const string DefaultApkName = "MR_System.apk";

    public static void BuildAndroidRelease()
    {
        string projectPath = Directory.GetCurrentDirectory();
        ApplySigningSettingsFromEnvironment();

        string outputDir = Environment.GetEnvironmentVariable("UNITY_ANDROID_BUILD_OUTPUT_DIR");
        if (string.IsNullOrWhiteSpace(outputDir))
        {
            outputDir = Path.Combine(projectPath, DefaultOutputDir);
        }

        string apkName = Environment.GetEnvironmentVariable("UNITY_ANDROID_BUILD_APK_NAME");
        if (string.IsNullOrWhiteSpace(apkName))
        {
            apkName = DefaultApkName;
        }

        Directory.CreateDirectory(outputDir);

        string[] scenes = EditorBuildSettingsScene.GetActiveSceneList(EditorBuildSettings.scenes);
        if (scenes == null || scenes.Length == 0)
        {
            throw new InvalidOperationException("No enabled scenes found in EditorBuildSettings.");
        }

        EditorUserBuildSettings.buildAppBundle = false;
        EditorUserBuildSettings.exportAsGoogleAndroidProject = false;
        EditorUserBuildSettings.androidBuildSystem = AndroidBuildSystem.Gradle;

        string outputPath = Path.Combine(outputDir, apkName);
        BuildPlayerOptions options = new BuildPlayerOptions
        {
            scenes = scenes,
            target = BuildTarget.Android,
            locationPathName = outputPath,
            options = BuildOptions.None
        };

        BuildReport report = BuildPipeline.BuildPlayer(options);
        BuildSummary summary = report.summary;

        if (summary.result != BuildResult.Succeeded)
        {
            throw new Exception($"Android build failed: {summary.result}, output={outputPath}");
        }

        long size = 0;
        if (File.Exists(outputPath))
        {
            size = new FileInfo(outputPath).Length;
        }

        Console.WriteLine($"ANDROID_BUILD_SUCCESS|{outputPath}|{size}");
    }

    static void ApplySigningSettingsFromEnvironment()
    {
        string keystorePath = Environment.GetEnvironmentVariable("UNITY_ANDROID_KEYSTORE_PATH");
        string keystorePass = Environment.GetEnvironmentVariable("UNITY_ANDROID_KEYSTORE_PASS");
        string keyaliasName = Environment.GetEnvironmentVariable("UNITY_ANDROID_KEYALIAS_NAME");
        string keyaliasPass = Environment.GetEnvironmentVariable("UNITY_ANDROID_KEYALIAS_PASS");

        if (string.IsNullOrWhiteSpace(keystorePath))
        {
            return;
        }

        if (!File.Exists(keystorePath))
        {
            throw new FileNotFoundException($"Keystore file not found: {keystorePath}");
        }

        if (string.IsNullOrWhiteSpace(keyaliasName))
        {
            throw new InvalidOperationException("UNITY_ANDROID_KEYALIAS_NAME is required when a keystore path is provided.");
        }

        PlayerSettings.Android.useCustomKeystore = true;
        PlayerSettings.Android.keystoreName = keystorePath;
        PlayerSettings.Android.keystorePass = keystorePass ?? string.Empty;
        PlayerSettings.Android.keyaliasName = keyaliasName;
        PlayerSettings.Android.keyaliasPass = keyaliasPass ?? string.Empty;
    }
}
