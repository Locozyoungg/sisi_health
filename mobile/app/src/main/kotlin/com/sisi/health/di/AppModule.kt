package com.sisi.health.di

import android.content.Context
import com.sisi.health.BuildConfig
import com.sisi.health.data.db.SisiDatabase
import com.sisi.health.data.prefs.SettingsStore
import com.sisi.health.data.repo.DiaryRepository
import com.sisi.health.data.security.KeyCipher
import com.sisi.health.data.sync.SisiApi
import com.sisi.health.engine.RuleEngine
import com.sisi.health.engine.RuleSource
import com.sisi.health.vault.VaultManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.kotlinx.serialization.asConverterFactory
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun json(): Json = Json { ignoreUnknownKeys = true }

    @Provides
    @Singleton
    fun settings(@ApplicationContext context: Context): SettingsStore = SettingsStore(context)

    @Provides
    @Singleton
    fun dbPassphrase(settings: SettingsStore): ByteArray {
        settings.dbPassphrase?.let { return KeyCipher.decrypt(it) }
        val fresh = KeyCipher.randomBytes(32)
        settings.dbPassphrase = KeyCipher.encrypt(fresh)
        return fresh
    }

    @Provides
    @Singleton
    fun database(@ApplicationContext context: Context, passphrase: ByteArray): SisiDatabase =
        SisiDatabase.get(context, passphrase)

    @Provides
    @Singleton
    fun okHttp(): OkHttpClient {
        val builder = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
        if (BuildConfig.DEBUG) {
            builder.addInterceptor(HttpLoggingInterceptor().apply { level = HttpLoggingInterceptor.Level.BASIC })
        }
        return builder.build()
    }

    @Provides
    @Singleton
    fun api(client: OkHttpClient, json: Json): SisiApi =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()
            .create(SisiApi::class.java)

    @Provides
    @Singleton
    fun ruleSource(@ApplicationContext context: Context): RuleSource = AndroidRuleSource(context)

    @Provides
    @Singleton
    fun ruleEngine(source: RuleSource): RuleEngine =
        RuleEngine(
            com.sisi.health.engine.RuleSetLoader.loadRules(source),
            com.sisi.health.engine.RULE_SET_VERSION,
            BuildConfig.ALLOW_UNVALIDATED_RULES,
        )

    @Provides
    @Singleton
    fun vaultManager(settings: SettingsStore): VaultManager = VaultManager(settings)

    @Provides
    @Singleton
    fun repository(db: SisiDatabase, api: SisiApi, json: Json): DiaryRepository =
        DiaryRepository(db.diaryDao(), db.syncStateDao(), api, json)
}

/** Ontology served from app assets at runtime (bundled by the copyOntologyAssets
 * Gradle task from /ontology — the single source of truth). */
class AndroidRuleSource(private val context: Context) : RuleSource {
    private val assets = context.assets

    override fun listFiles(dir: String): List<String> = assets.list(dir)?.toList() ?: emptyList()

    override fun readText(path: String): String =
        assets.open(path).bufferedReader(Charsets.UTF_8).use { it.readText() }
}
