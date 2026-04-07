package com.paul.facescan

import android.Manifest
import android.content.SharedPreferences
import android.content.pm.PackageManager
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.ImageView
import android.widget.TextView
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.preference.PreferenceManager
import okhttp3.Call
import okhttp3.Callback
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.IOException
import java.util.concurrent.TimeUnit

class MainActivity : ComponentActivity() {

    private lateinit var prefs: SharedPreferences
    private lateinit var serverUrlField: EditText
    private lateinit var personNameField: EditText
    private lateinit var imagePreview: ImageView
    private lateinit var output: TextView

    private val http: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(60, TimeUnit.SECONDS)
        .build()

    /** What we'll do once a picked image comes back. */
    private enum class PendingAction { NONE, RECOGNIZE, ENROLL }
    private var pendingAction: PendingAction = PendingAction.NONE

    private val pickImageLauncher = registerForActivityResult(
        ActivityResultContracts.GetContent()
    ) { uri: Uri? ->
        if (uri != null) handleSelectedImage(uri)
    }

    private val takePictureLauncher = registerForActivityResult(
        ActivityResultContracts.TakePicturePreview()
    ) { bitmap: Bitmap? ->
        if (bitmap != null) handleCapturedBitmap(bitmap)
    }

    private val cameraPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) takePictureLauncher.launch(null)
        else toast("Camera permission denied")
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = PreferenceManager.getDefaultSharedPreferences(this)
        serverUrlField = findViewById(R.id.serverUrl)
        personNameField = findViewById(R.id.personName)
        imagePreview = findViewById(R.id.imagePreview)
        output = findViewById(R.id.output)

        serverUrlField.setText(prefs.getString(KEY_URL, ""))

        findViewById<Button>(R.id.btnSaveUrl).setOnClickListener {
            prefs.edit().putString(KEY_URL, serverUrlField.text.toString().trim()).apply()
            toast("Saved")
            checkHealth()
        }

        findViewById<Button>(R.id.btnPickRecognize).setOnClickListener {
            pendingAction = PendingAction.RECOGNIZE
            pickImageLauncher.launch("image/*")
        }
        findViewById<Button>(R.id.btnCameraRecognize).setOnClickListener {
            pendingAction = PendingAction.RECOGNIZE
            launchCamera()
        }
        findViewById<Button>(R.id.btnEnrollGallery).setOnClickListener {
            if (personNameField.text.isBlank()) {
                toast("Enter a person name first"); return@setOnClickListener
            }
            pendingAction = PendingAction.ENROLL
            pickImageLauncher.launch("image/*")
        }
        findViewById<Button>(R.id.btnEnrollCamera).setOnClickListener {
            if (personNameField.text.isBlank()) {
                toast("Enter a person name first"); return@setOnClickListener
            }
            pendingAction = PendingAction.ENROLL
            launchCamera()
        }
        findViewById<Button>(R.id.btnListPeople).setOnClickListener {
            listPeople()
        }
    }

    // ---------- Image acquisition ----------

    private fun launchCamera() {
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.CAMERA
        ) == PackageManager.PERMISSION_GRANTED
        if (granted) takePictureLauncher.launch(null)
        else cameraPermissionLauncher.launch(Manifest.permission.CAMERA)
    }

    private fun handleSelectedImage(uri: Uri) {
        val bytes = contentResolver.openInputStream(uri)?.use { it.readBytes() }
            ?: run { toast("Could not read image"); return }
        val bitmap = BitmapFactory.decodeByteArray(bytes, 0, bytes.size)
        imagePreview.setImageBitmap(bitmap)
        dispatchPending(bytes)
    }

    private fun handleCapturedBitmap(bitmap: Bitmap) {
        imagePreview.setImageBitmap(bitmap)
        val baos = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, 90, baos)
        dispatchPending(baos.toByteArray())
    }

    private fun dispatchPending(imageBytes: ByteArray) {
        when (pendingAction) {
            PendingAction.RECOGNIZE -> sendRecognize(imageBytes)
            PendingAction.ENROLL -> sendEnroll(imageBytes, personNameField.text.toString().trim())
            PendingAction.NONE -> {}
        }
        pendingAction = PendingAction.NONE
    }

    // ---------- Networking ----------

    private fun serverUrl(): String? {
        val url = prefs.getString(KEY_URL, "")?.trim().orEmpty()
        if (url.isEmpty()) {
            toast("Set the server URL first")
            return null
        }
        return url.trimEnd('/')
    }

    private fun checkHealth() {
        val base = serverUrl() ?: return
        val req = Request.Builder().url("$base/health").build()
        http.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) =
                runOnUiThread { setOutput("Server unreachable: ${e.message}") }

            override fun onResponse(call: Call, response: Response) {
                val body = response.body?.string().orEmpty()
                runOnUiThread { setOutput("Health: $body") }
            }
        })
    }

    private fun sendRecognize(imageBytes: ByteArray) {
        val base = serverUrl() ?: return
        setOutput("Recognizing…")
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart(
                "file", "image.jpg",
                imageBytes.toRequestBody("image/jpeg".toMediaTypeOrNull())
            )
            .build()
        val req = Request.Builder().url("$base/recognize").post(body).build()
        http.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) =
                runOnUiThread { setOutput("Network error: ${e.message}") }

            override fun onResponse(call: Call, response: Response) {
                val raw = response.body?.string().orEmpty()
                runOnUiThread { setOutput(formatRecognizeResponse(raw)) }
            }
        })
    }

    private fun sendEnroll(imageBytes: ByteArray, name: String) {
        val base = serverUrl() ?: return
        setOutput("Enrolling $name…")
        val body = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("name", name)
            .addFormDataPart(
                "files", "image.jpg",
                imageBytes.toRequestBody("image/jpeg".toMediaTypeOrNull())
            )
            .build()
        val req = Request.Builder().url("$base/enroll").post(body).build()
        http.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) =
                runOnUiThread { setOutput("Network error: ${e.message}") }

            override fun onResponse(call: Call, response: Response) {
                val raw = response.body?.string().orEmpty()
                runOnUiThread { setOutput("Enroll result:\n$raw") }
            }
        })
    }

    private fun listPeople() {
        val base = serverUrl() ?: return
        val req = Request.Builder().url("$base/people").build()
        http.newCall(req).enqueue(object : Callback {
            override fun onFailure(call: Call, e: IOException) =
                runOnUiThread { setOutput("Network error: ${e.message}") }

            override fun onResponse(call: Call, response: Response) {
                val raw = response.body?.string().orEmpty()
                runOnUiThread { setOutput(formatPeopleResponse(raw)) }
            }
        })
    }

    // ---------- Formatting ----------

    private fun formatRecognizeResponse(raw: String): String {
        return try {
            val json = JSONObject(raw)
            val faces = json.optJSONArray("faces") ?: JSONArray()
            if (faces.length() == 0) "No faces detected."
            else buildString {
                append("Found ${faces.length()} face(s):\n")
                for (i in 0 until faces.length()) {
                    val f = faces.getJSONObject(i)
                    val name = f.optString("name", "Unknown")
                    val conf = (f.optDouble("confidence", 0.0) * 100).toInt()
                    append("  ${i + 1}. $name ($conf%)\n")
                }
            }
        } catch (e: Exception) { raw }
    }

    private fun formatPeopleResponse(raw: String): String {
        return try {
            val arr = JSONArray(raw)
            if (arr.length() == 0) "(no people enrolled yet)"
            else buildString {
                append("Enrolled people:\n")
                for (i in 0 until arr.length()) {
                    val p = arr.getJSONObject(i)
                    append("  - ${p.getString("name")}  (${p.getInt("num_encodings")} faces)\n")
                }
            }
        } catch (e: Exception) { raw }
    }

    // ---------- Misc ----------

    private fun setOutput(text: String) { output.text = text }
    private fun toast(text: String) =
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()

    companion object {
        private const val KEY_URL = "server_url"
    }
}
