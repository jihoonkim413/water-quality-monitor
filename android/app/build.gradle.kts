import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

// Personal defaults (server + Cloudflare service token) come from a git-ignored
// file so they never end up in the repo. See secrets.example.properties.
val secrets = Properties().apply {
    val f = rootProject.file("secrets.properties")
    if (f.exists()) f.inputStream().use { load(it) }
}

fun quoted(key: String, fallback: String = "") =
    "\"" + (secrets.getProperty(key)?.trim()?.ifEmpty { null } ?: fallback) + "\""

android {
    namespace = "com.jihoonkim.water"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.jihoonkim.water"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        buildConfigField("String", "DEFAULT_SERVER", quoted("server", "https://water.jihoon-kim.com"))
        buildConfigField("String", "DEFAULT_CLIENT_ID", quoted("cfClientId"))
        buildConfigField("String", "DEFAULT_CLIENT_SECRET", quoted("cfClientSecret"))
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation(platform("androidx.compose:compose-bom:2026.08.00"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.activity:activity-compose:1.12.4")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.10.0")
    implementation("androidx.work:work-runtime-ktx:2.11.2")
}
