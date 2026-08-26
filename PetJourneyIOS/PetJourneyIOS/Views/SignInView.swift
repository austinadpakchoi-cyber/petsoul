import AuthenticationServices
import SwiftUI

/// 登录页：账号是「接收 TA」的入口。
/// 登录后，宠物的照片、路线和回忆都跟着账号走——换设备、重装 App，TA 都还在，
/// 数据由账号决定，而不是设备里的固定演示。
struct SignInView: View {
    @EnvironmentObject private var session: AppSessionStore

    let service: any PetJourneyService
    var onSignedIn: (AuthSessionResponse) -> Void

    @State private var isSigningIn = false
    @State private var errorMessage: String?

    var body: some View {
        ZStack {
            AppBackground()

            AmbientSignalField(
                tint: DesignTokens.sea,
                warmth: DesignTokens.pollen,
                density: 16,
                drift: 0.52
            )
            .opacity(0.48)

            VStack(spacing: 0) {
                Spacer()

                VStack(spacing: 14) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .font(.system(size: 42, weight: .medium))
                        .foregroundStyle(DesignTokens.sage)
                        .padding(.bottom, 4)

                    Text("先登录，再接 TA 回家")
                        .font(.system(size: 31, weight: .semibold, design: .rounded))
                        .foregroundStyle(DesignTokens.ink)
                        .multilineTextAlignment(.center)

                    Text("登录后，TA 的照片、路线和回忆会跟着你的账号走。换设备、重装 App，TA 都还在，也不会串到别人的旅程里。")
                        .font(.subheadline)
                        .foregroundStyle(DesignTokens.secondaryInk)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                        .padding(.horizontal, 8)
                }
                .padding(.horizontal, DesignTokens.pagePadding)
                .padding(.bottom, 34)

                VStack(spacing: 12) {
                    SignInWithAppleButton(.signIn) { request in
                        request.requestedScopes = [.fullName, .email]
                    } onCompletion: { result in
                        handleAppleCompletion(result)
                    }
                    .signInWithAppleButtonStyle(.black)
                    .frame(height: 52)
                    .clipShape(RoundedRectangle(cornerRadius: DesignTokens.controlRadius, style: .continuous))
                    .disabled(isSigningIn)

                    if isSigningIn {
                        HStack(spacing: 8) {
                            ProgressView()
                            Text("正在接通你的信号站")
                                .font(.footnote)
                                .foregroundStyle(DesignTokens.secondaryInk)
                        }
                    }

                    if let errorMessage {
                        Text(errorMessage)
                            .font(.footnote)
                            .foregroundStyle(DesignTokens.dusk)
                            .multilineTextAlignment(.center)
                            .padding(.top, 4)
                    }

                    #if DEBUG
                    debugLocalControls
                    #endif
                }
                .padding(.horizontal, DesignTokens.pagePadding)

                Spacer()
                Spacer()
            }
        }
    }

    private func handleAppleCompletion(_ result: Result<ASAuthorization, Error>) {
        switch result {
        case .success(let authorization):
            guard
                let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                let tokenData = credential.identityToken,
                let identityToken = String(data: tokenData, encoding: .utf8)
            else {
                errorMessage = "这次没有收到 Apple 的信号，请再试一次。"
                return
            }
            var parts: [String] = []
            if let given = credential.fullName?.givenName, !given.isEmpty {
                parts.append(given)
            }
            if let family = credential.fullName?.familyName, !family.isEmpty {
                parts.append(family)
            }
            let displayName = parts.joined(separator: " ")
            Task {
                await signIn(identityToken: identityToken, displayName: displayName.isEmpty ? nil : displayName)
            }
        case .failure:
            errorMessage = "登录没有完成，可以再试一次。"
        }
    }

    private func signIn(identityToken: String, displayName: String?) async {
        isSigningIn = true
        errorMessage = nil
        do {
            let auth = try await service.signInWithApple(
                request: AppleSignInRequest(identityToken: identityToken, displayName: displayName)
            )
            session.storeAuthSession(token: auth.accessToken, userID: auth.userID, displayName: auth.displayName)
            isSigningIn = false
            onSignedIn(auth)
        } catch {
            isSigningIn = false
            errorMessage = "信号没有接通，请稍后再试。"
        }
    }

    #if DEBUG
    private var debugLocalControls: some View {
        VStack(spacing: 10) {
            Divider()
                .overlay(DesignTokens.softLine)

            Text("本地联调")
                .font(.caption.weight(.semibold))
                .foregroundStyle(DesignTokens.secondaryInk)

            Button {
                Task {
                    await signIn(identityToken: "mock-apple-sub:local-dev", displayName: "本地旅人")
                }
            } label: {
                Label("以开发身份直接进入（mock 登录）", systemImage: "laptopcomputer")
                    .font(.subheadline.weight(.medium))
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.bordered)

            Text("后端地址可通过 PETJOURNEY_BASE_URL 环境变量指向本机。")
                .font(.caption2)
                .foregroundStyle(DesignTokens.secondaryInk.opacity(0.8))
        }
        .padding(.top, 14)
    }
    #endif
}
