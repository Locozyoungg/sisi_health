import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlinx.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
}

// The ontology is the single source of truth for rules/golden cases/red flags.
// The app bundles the same JSON the backend runs (spec: identical engines).
// Single-root copy preserves the rules/golden/redflags/schema subdirectories.
val copyOntologyAssets by tasks.registering(Copy::class) {
    from("../../ontology") {
        include("rules/**", "golden/**", "redflags/**", "schema/**")
    }
    into("src/main/assets/ontology")
}

val copyOntologyTestResources by tasks.registering(Copy::class) {
    from("../../ontology") {
        include("rules/**", "golden/**", "redflags/**", "schema/**")
    }
    into("src/test/resources/ontology")
}

tasks.named("preBuild") {
    dependsOn(copyOntologyAssets, copyOntologyTestResources)
}

android {
    namespace = "com.sisi.health"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.sisi.health"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        debug {
            // Emulator loopback for local dev; no production endpoints are ever hard-coded.
            buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:8000\"")
            buildConfigField("boolean", "ALLOW_UNVALIDATED_RULES", "true")
        }
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            // Placeholder: real pilot endpoint is supplied at signing time via
            // -PapiBaseUrl=... (never committed; see docs/assumptions.md A5-adjacent note).
            buildConfigField("String", "API_BASE_URL", "\"https://api.sisi-health.example\"")
            buildConfigField("boolean", "ALLOW_UNVALIDATED_RULES", "false")
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(JvmTarget.JVM_17)
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
        }
    }
}

ksp {
    arg("room.schemaLocation", "$projectDir/schemas")
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.ui)
    implementation(libs.compose.ui.graphics)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.material.icons)

    implementation(libs.room.runtime)
    implementation(libs.room.ktx)
    ksp(libs.room.compiler)
    implementation(libs.sqlcipher)
    implementation(libs.androidx.sqlite)

    implementation(libs.work.runtime)
    implementation(libs.hilt.work)
    ksp(libs.hilt.work.compiler)

    implementation(libs.retrofit)
    implementation(libs.retrofit.kotlinx)
    implementation(libs.okhttp)
    implementation(libs.okhttp.logging)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.navigation.compose)

    testImplementation(libs.junit)
    testImplementation(libs.kotest.property)
    testImplementation(libs.robolectric)
    testImplementation(libs.androidx.test.core)
    testImplementation(libs.kotlinx.coroutines.android)

    androidTestImplementation(libs.androidx.test.core)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.espresso.core)
}
