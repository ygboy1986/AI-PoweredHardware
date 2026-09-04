import XCTest
@testable import GuardianIOS

final class GuardianAPIClientTests: XCTestCase {
    func testHighHeartRateReturnsConfirmationRequirement() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let client = GuardianAPIClient(baseURL: URL(string: "https://guardian.test/")!, session: session)

        MockURLProtocol.handler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.url?.path, "/v1/devices/1001/health-analysis")
            let response = HTTPURLResponse(url: request.url!, statusCode: 200,
                                           httpVersion: nil, headerFields: ["Content-Type": "application/json"])!
            let json = """
            {"request_id":"request-1","device_id":1001,"risk_level":"high","confidence":0.95,
            "reasons":["心率偏高"],"requires_human_confirmation":true,"fallback_used":false}
            """
            return (response, Data(json.utf8))
        }

        let snapshot = HealthSnapshot(
            readings: [HealthReading(metric: "heart_rate", value: 132, unit: "bpm",
                                     measuredAt: .now, source: "watch")],
            trajectory: [], hasSuspectedFall: false
        )
        let report = try await client.analyzeHealth(deviceID: 1001, snapshot: snapshot)
        XCTAssertEqual(report.riskLevel, "high")
        XCTAssertTrue(report.requiresHumanConfirmation)
    }
}

final class MockURLProtocol: URLProtocol {
    static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            guard let handler = Self.handler else { fatalError("Missing mock handler") }
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }
    override func stopLoading() { }
}
