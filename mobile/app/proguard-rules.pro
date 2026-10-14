# SISI Health — R8 rules (Phase 2). No patient data ever logged or serialized in
# release crash reporting; keep serializable DTOs.
-keepattributes Signature
-keep class com.sisi.health.data.sync.dto.** { *; }
-keep class com.sisi.health.engine.** { *; }
