import Foundation

// MARK: - Request models

struct HealthReading: Codable, Sendable {
    let metric: String
    let value: Double
    let unit: String
    let measuredAt: Date
    let source: String

    enum CodingKeys: String, CodingKey {
        case metric, value, unit, source
        case measuredAt = "measured_at"
    }
}

struct TrajectoryPoint: Codable, Sendable {
    let latitude: Double
    let longitude: Double
    let accuracyM: Double
    let recordedAt: Date

    enum CodingKeys: String, CodingKey {
        case latitude, longitude
        case accuracyM = "accuracy_m"
        case recordedAt = "recorded_at"
    }
}

struct HealthSnapshot: Codable, Sendable {
    let readings: [HealthReading]
    let trajectory: [TrajectoryPoint]
    let hasSuspectedFall: Bool

    enum CodingKeys: String, CodingKey {
        case readings, trajectory
        case hasSuspectedFall = "has_suspected_fall"
    }
}

// MARK: - Response models

struct GuardianRiskReport: Codable, Sendable {
    let requestID: String
    let deviceID: Int
    let riskLevel: String
    let confidence: Double
    let reasons: [String]
    let requiresHumanConfirmation: Bool
    let fallbackUsed: Bool

    enum CodingKeys: String, CodingKey {
        case confidence, reasons
        case requestID = "request_id"
        case deviceID = "device_id"
        case riskLevel = "risk_level"
        case requiresHumanConfirmation = "requires_human_confirmation"
        case fallbackUsed = "fallback_used"
    }
}

enum GuardianAPIError: LocalizedError {
    case invalidResponse
    case server(statusCode: Int, message: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "服务器返回格式无效"
        case let .server(statusCode, message): return "服务器错误 \(statusCode)：\(message)"
        }
    }
}

actor GuardianAPIClient {
    private let baseURL: URL
    private let session: URLSession

    init(baseURL: URL, session: URLSession = .shared) {
        self.baseURL = baseURL
        self.session = session
    }

    func analyzeHealth(deviceID: Int, snapshot: HealthSnapshot) async throws -> GuardianRiskReport {
        let url = baseURL.appending(path: "v1/devices/\(deviceID)/health-analysis")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.timeoutInterval = 10

        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        request.httpBody = try encoder.encode(snapshot)

        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw GuardianAPIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? ""
            throw GuardianAPIError.server(statusCode: http.statusCode, message: message)
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return try decoder.decode(GuardianRiskReport.self, from: data)
    }
}
