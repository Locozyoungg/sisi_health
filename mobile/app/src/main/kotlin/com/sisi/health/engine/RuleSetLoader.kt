package com.sisi.health.engine

import kotlinx.serialization.json.Json

/** Source of ontology files: Android assets at runtime, classpath resources in JVM
 * tests. Paths are relative to the ontology root (rules/, golden/, redflags/). */
interface RuleSource {
    fun listFiles(dir: String): List<String>
    fun readText(path: String): String
}

object RuleSetLoader {
    private val json = Json { ignoreUnknownKeys = true }

    fun loadRules(source: RuleSource): List<Rule> =
        source.listFiles("rules")
            .filter { it.endsWith(".json") }
            .sorted()
            .map { name -> json.decodeFromString<Rule>(source.readText("rules/$name")) }

    fun loadGoldenFile(source: RuleSource): GoldenFile =
        json.decodeFromString(source.readText("golden/cases.json"))

    fun loadPatternFiles(source: RuleSource): List<RedFlagPatternFile> =
        source.listFiles("redflags")
            .filter { it.endsWith(".json") }
            .sorted()
            .map { name -> json.decodeFromString(source.readText("redflags/$name")) }

    fun buildEngine(source: RuleSource, allowUnvalidated: Boolean): RuleEngine =
        RuleEngine(loadRules(source), RULE_SET_VERSION, allowUnvalidated)
}
