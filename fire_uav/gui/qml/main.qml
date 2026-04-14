import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Dialogs
import QtWebEngine 1.10
import Qt5Compat.GraphicalEffects
import QtQuick.Shapes 1.15

ApplicationWindow {
    id: root
    width: 1440
    height: 860
    visible: true
    title: "fire_uav"
    color: "transparent"

    property real baseSpacing: 16
    property color panelColor: "#111111"
    property color borderColor: "#333333"
    property color textPrimary: "#ffffff"
    property color textMuted: "#aaaaaa"
    property color mapGlassFill: Qt.rgba(0.04, 0.04, 0.04, 0.40)
    property color mapGlassFillStrong: Qt.rgba(0.04, 0.04, 0.04, 0.52)
    property color mapGlassBorder: Qt.rgba(1, 1, 1, 0.18)
    property int cardRadius: 18
    property int currentTab: 1
    property bool hasApp: typeof app !== "undefined" && app !== null
    property string missionState: hasApp ? app.missionState : "PREFLIGHT"
    property bool isPreflight: missionState === "PREFLIGHT"
    property bool isReady: missionState === "READY"
    property bool isInFlight: missionState === "IN_FLIGHT"
    property bool isRtl: missionState === "RTL"
    property bool isPostflight: missionState === "POSTFLIGHT"
    property bool planConfirmed: hasApp ? app.planConfirmed : false
    property bool bridgeModeEnabled: hasApp ? app.bridgeModeEnabled : false
    property bool homePickModeActive: hasApp ? app.homePickModeEnabled : false
    property bool manualTargetModeActive: hasApp ? app.objectSpawnModeEnabled : false
    property bool mapNeedsRefresh: hasApp ? app.mapRefreshNeeded : false
    property bool toastVisible: false
    property string toastTitle: "Notification"
    property string toastMessage: ""
    property var orbitSelection: []
    property bool confirmPlanSheetVisible: false
    property bool orbitSelectionSheetVisible: false
    property bool lastRouteEditMode: false
    property bool overlayActive: false

    onCurrentTabChanged: {
        if (hasApp) app.setVideoVisible(currentTab === 0);
    }

    function runMapTool(name, arg) {
        if (!mapView) return;
        var callArg = (arg === undefined) ? "" : JSON.stringify(arg);
        var js = "window.__mapTools && window.__mapTools." + name
               + " && window.__mapTools." + name + "(" + callArg + ")";
        mapView.runJavaScript(js);
    }

    function requestConfirmPlan() {
        if (!hasApp) return;
        confirmPlanSheetVisible = true;
    }

    function requestOrbit() {
        if (!hasApp) return;
        if (app.confirmedObjectCount > 1) {
            orbitSelection = [];
            orbitSelectionSheetVisible = true;
        } else {
            app.orbitConfirmedObject();
        }
    }

    function toggleOrbitSelection(objectId) {
        var next = orbitSelection.slice(0);
        var idx = next.indexOf(objectId);
        if (idx === -1) {
            next.push(objectId);
        } else {
            next.splice(idx, 1);
        }
        orbitSelection = next;
    }
    Connections {
        target: hasApp ? app : null
        function onFlightControlsChanged() {
            if (!hasApp) return;
            var next = app.routeEditMode;
            if (next === root.lastRouteEditMode) return;
            root.lastRouteEditMode = next;
            runMapTool("setAppendMode", next);
            if (next) {
                runMapTool("drawPath");
            } else {
                runMapTool("stopDraw");
            }
        }
    }

    Component {
        id: overlayActionButton

        Item {
            id: overlayActionButtonRoot
            property string label
            property var action
            property bool accent: false
            property bool hovered: false
            property bool pressed: false

            Layout.fillWidth: true
            implicitHeight: 44
            opacity: enabled ? 1.0 : 0.48
            scale: pressed && enabled ? 0.985 : 1.0
            clip: true
            layer.enabled: true
            layer.smooth: true
            Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

            Rectangle {
                anchors.fill: parent
                radius: 14
                color: overlayActionButtonRoot.accent
                       ? Qt.rgba(0.26, 0.58, 0.94, overlayActionButtonRoot.hovered ? 0.34 : 0.26)
                       : Qt.rgba(1, 1, 1, overlayActionButtonRoot.hovered ? 0.12 : 0.07)
                border.color: overlayActionButtonRoot.accent
                              ? Qt.rgba(0.62, 0.83, 1.0, 0.56)
                              : Qt.rgba(1, 1, 1, 0.12)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: 14
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.03) }
                }
                opacity: overlayActionButtonRoot.pressed ? 0.18 : 0.1
            }

            Text {
                anchors.centerIn: parent
                text: overlayActionButtonRoot.label
                color: overlayActionButtonRoot.accent ? "#eff7ff" : textPrimary
                font.pixelSize: 13
                font.family: "Inter"
                font.bold: true
            }

            MouseArea {
                anchors.fill: parent
                enabled: overlayActionButtonRoot.enabled
                hoverEnabled: true
                onEntered: overlayActionButtonRoot.hovered = true
                onExited: {
                    overlayActionButtonRoot.hovered = false;
                    overlayActionButtonRoot.pressed = false;
                }
                onPressed: overlayActionButtonRoot.pressed = true
                onReleased: overlayActionButtonRoot.pressed = false
                onClicked: {
                    if (overlayActionButtonRoot.action) overlayActionButtonRoot.action();
                }
            }
        }
    }

    Item {
        id: sceneLayer
        anchors.fill: parent

        Rectangle { anchors.fill: parent; color: "#000000" }

        Rectangle {
            id: debugLauncher
            width: 176
            height: 44
            radius: height / 2
            anchors.top: parent.top
            anchors.right: parent.right
            anchors.topMargin: 22
            anchors.rightMargin: 24
            color: "transparent"
            z: 200
            clip: true
            antialiasing: true
            layer.enabled: true
            layer.smooth: true

            ShaderEffectSource {
                id: debugSlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(debugLauncher.x, debugLauncher.y, debugLauncher.width, debugLauncher.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: debugBlur
                anchors.fill: parent
                source: debugSlice
                radius: 18
                transparentBorder: true
                visible: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: debugBlur
                maskSource: Rectangle {
                    width: debugLauncher.width
                    height: debugLauncher.height
                    radius: debugLauncher.radius
                }
                z: -2
            }

            Rectangle {
                anchors.fill: parent
                radius: debugLauncher.radius
                color: Qt.rgba(0.08, 0.08, 0.08, 0.18)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
                z: -1
            }

            Rectangle {
                anchors.fill: parent
                radius: debugLauncher.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.16) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.07) }
                }
                opacity: debugMouse.containsMouse ? 0.30 : 0.18
                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
            }

            Row {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 16
                spacing: 10

                Rectangle {
                    width: 12
                    height: 12
                    radius: 6
                    color: hasApp && app.debugMode ? "#67e8a9" : "#fbbf24"
                    border.color: Qt.rgba(1, 1, 1, 0.2)
                    anchors.verticalCenter: parent.verticalCenter
                }

                Column {
                    width: parent.width - 22
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    clip: true

                    Text {
                        text: "Debug console"
                        color: textPrimary
                        font.pixelSize: 13
                        font.family: "Inter"
                        font.weight: Font.Medium
                        elide: Text.ElideRight
                        width: parent.width
                    }
                    Text {
                        text: hasApp && app.debugMode ? "Flight loop running" : "Flight loop idle"
                        color: textMuted
                        font.pixelSize: 11
                        font.family: "Inter"
                        elide: Text.ElideRight
                        width: parent.width
                    }
                }
            }

            MouseArea {
                id: debugMouse
                anchors.fill: parent
                hoverEnabled: true
                onClicked: {
                    debugWindow.visible = true;
                    debugWindow.raise();
                }
            }
        }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: baseSpacing / 2

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: currentTab

                // Detector
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Rectangle {
                        anchors.fill: parent
                        radius: cardRadius
                        color: panelColor
                        border.color: borderColor
                        clip: true

                        Item {
                            id: videoSurface
                            anchors.fill: parent

                            Image {
                                id: videoView
                                anchors.fill: parent
                                fillMode: Image.PreserveAspectFit
                                cache: false
                                smooth: true
                                source: hasApp && app.cameraAvailable ? "image://video/live" : ""
                                visible: hasApp && app.cameraAvailable
                            }
                        }
                        Connections {
                            target: hasApp ? app : null
                            function onFrameReady(url) { videoView.source = url; }
                        }

                        Rectangle {
                            anchors.fill: parent
                            color: Qt.rgba(0, 0, 0, 0.7)
                            visible: (!hasApp || !app.cameraAvailable) || videoView.status !== Image.Ready
                            z: 5
                            Text {
                                anchors.centerIn: parent
                                text: hasApp ? app.cameraStatusDetail : "Camera not found"
                                color: textPrimary
                                font.pixelSize: 24
                                font.bold: true
                            }
                        }

                        Item {
                            id: statusBar
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 12
                            width: Math.min(root.width * 0.34, 320)
                            height: navFloating.height
                            z: 7
                            property real highlightOpacity: 0.25
                            property color pillBg: Qt.rgba(1, 1, 1, 0.08)
                            property color pillBorder: Qt.rgba(1, 1, 1, 0.18)
                            property var blurOrigin: {
                                var _x = statusBar.x;
                                var _y = statusBar.y;
                                return statusBar.mapToItem(videoSurface, 0, 0);
                            }

                            ShaderEffectSource {
                                id: statusSlice
                                anchors.fill: parent
                                sourceItem: root.currentTab === 0 ? videoSurface : null
                                sourceRect: Qt.rect(statusBar.blurOrigin.x, statusBar.blurOrigin.y, statusBar.width, statusBar.height)
                                recursive: true
                                live: root.currentTab === 0 && root.visible
                                visible: false
                            }

                            FastBlur {
                                id: statusBlur
                                anchors.fill: parent
                                source: statusSlice
                                radius: 16
                                transparentBorder: true
                                visible: root.currentTab === 0
                                z: -3
                            }

                            OpacityMask {
                                anchors.fill: parent
                                source: statusBlur
                                maskSource: Rectangle {
                                    width: statusBar.width
                                    height: statusBar.height
                                    radius: height / 2
                                }
                                z: -2
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: height / 2
                                color: mapGlassFill
                                border.color: mapGlassBorder
                                border.width: 1
                                z: -1
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: height / 2
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.06) }
                                }
                                opacity: statusBar.highlightOpacity
                                Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                z: -0.5
                            }

                            Row {
                                id: statusRow
                                anchors.fill: parent
                                anchors.margins: 12
                                spacing: 0

                                Repeater {
                                    model: [
                                        { label: "FPS", value: function() { return hasApp ? app.fps.toFixed(1) : "0.0"; }, color: textPrimary },
                                        { label: "Latency", value: function() { return hasApp ? (app.latencyMs.toFixed(0) + " ms") : "n/a"; }, color: textPrimary },
                                        { label: "Conf", value: function() { return hasApp ? (Math.round(app.detectionConfidence * 100) + "%") : "0%"; }, color: "#7bc6ff" }
                                    ]
                                    delegate: Column {
                                        width: statusRow.width / 3
                                        anchors.verticalCenter: parent.verticalCenter
                                        spacing: 2
                                        Text {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: modelData.label
                                            color: Qt.rgba(1, 1, 1, 0.82)
                                            font.pixelSize: 13
                                            font.family: "Inter"
                                            font.weight: Font.Medium
                                        }
                                        Text {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            text: modelData.value()
                                            color: modelData.color
                                            font.pixelSize: 15
                                            font.family: "Inter"
                                            font.weight: Font.Medium
                                        }
                                    }
                                }
                            }
                        }

                        // Auto-run detector with fixed confidence
                        Component.onCompleted: {
                            if (hasApp && app.confidence !== 0.2) app.setConfidence(0.2);
                            if (hasApp && app.cameraAvailable) app.startDetector();
                        }
                    }
                }

                // Planner
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Rectangle {
                        anchors.fill: parent
                        radius: cardRadius
                        color: panelColor
                        border.color: borderColor
                        clip: true

                        WebEngineView {
                            id: mapView
                            anchors.fill: parent
                            url: hasApp ? app.mapUrl : ""
                            profile: WebEngineProfile { storageName: "fire-uav"; offTheRecord: true }
                            backgroundColor: "transparent"
                            property var mapConsoleQueue: []
                            settings {
                                localContentCanAccessRemoteUrls: true
                                localContentCanAccessFileUrls: true
                                javascriptEnabled: true
                                errorPageEnabled: true
                                webGLEnabled: true
                            }
                            Timer {
                                id: mapConsoleFlush
                                interval: 0
                                running: false
                                repeat: false
                                onTriggered: {
                                    if (!hasApp || mapView.mapConsoleQueue.length === 0) return;
                                    var pending = mapView.mapConsoleQueue.slice(0);
                                    mapView.mapConsoleQueue = [];
                                    for (var i = 0; i < pending.length; i++) {
                                        app.handleMapConsole(pending[i]);
                                    }
                                }
                            }
                            onLoadingChanged: function(loadRequest) {
                                if (loadRequest.status === WebEngineView.LoadSucceededStatus) {
                                    mapOverlay.text = ""
                                    if (hasApp) mapView.runJavaScript(app.mapBridgeScript);
                                } else if (loadRequest.status === WebEngineView.LoadFailedStatus || loadRequest.status === WebEngineView.LoadStoppedStatus) {
                                    mapOverlay.text = "Map failed: " + (loadRequest.errorString || "")
                                    console.warn("Map load failed", loadRequest.errorString)
                                } else {
                                    mapOverlay.text = "Map loading..."
                                }
                            }
                            onRenderProcessTerminated: function(terminationStatus, exitCode) {
                                mapOverlay.text = "Map renderer crashed"
                                console.error("WebEngine terminated", terminationStatus, exitCode)
                            }
                            onJavaScriptConsoleMessage: function(level, message, lineNumber, sourceID) {
                                if (message.indexOf("PY_") === 0) {
                                    mapView.mapConsoleQueue.push(message);
                                    if (!mapConsoleFlush.running) mapConsoleFlush.start();
                                }
                                if (message.indexOf("Leaflet failed") !== -1 || message.indexOf("OpenLayers failed") !== -1 || message.indexOf("Map instance not found") !== -1) {
                                    mapOverlay.text = message;
                                }
                                if (message.indexOf("Tile load failed") !== -1) {
                                    mapOverlay.text = "Map tiles unavailable (check network/offline cache)";
                                }
                                if (level === WebEngineView.ErrorMessageLevel) {
                                    console.error("Map JS error", message, lineNumber, sourceID)
                                }
                            }
                        }

                        Item {
                            id: mapClickOverlay
                            anchors.fill: parent
                            z: 4
                            property bool overlayActive: root.hasApp && (root.homePickModeActive || root.manualTargetModeActive)
                            visible: mapClickOverlay.overlayActive
                            MouseArea {
                                anchors.fill: parent
                                enabled: mapClickOverlay.overlayActive
                                hoverEnabled: true
                                acceptedButtons: Qt.LeftButton
                                onClicked: {
                                    if (!root.hasApp) return;
                                    var script = "window.__mapTools && window.__mapTools.screenToGeo(" + mouse.x + "," + mouse.y + ")";
                                    mapView.runJavaScript(script, function(result) {
                                        if (!result || typeof result.lat !== "number" || typeof result.lon !== "number") return;
                                        if (root.homePickModeActive) {
                                            app.setHomeFromMap(result.lat, result.lon);
                                        } else if (root.manualTargetModeActive) {
                                            app.spawnManualTargetAt(result.lat, result.lon);
                                        }
                                    });
                                }
                            }

                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 20
                                radius: 12
                                color: Qt.rgba(0, 0, 0, 0.65)
                                visible: mapClickOverlay.overlayActive
                                implicitWidth: hintText.implicitWidth + 24
                                implicitHeight: hintText.implicitHeight + 14

                                Text {
                                    id: hintText
                                    anchors.centerIn: parent
                                    text: root.homePickModeActive
                                          ? "Click map to set home"
                                          : root.manualTargetModeActive ? "Click map to spawn a manual target" : ""
                                    color: "#f8fafc"
                                    font.pixelSize: 13
                                    font.family: "Inter"
                                }
                            }
                        }

                        Item {
                            id: mapControls
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.top: parent.top
                            anchors.topMargin: 12
                            property real activeRowWidth: isPostflight ? postflightRow.implicitWidth
                                                              : (isRtl ? rtlRow.implicitWidth
                                                              : (isInFlight ? flightRow.implicitWidth
                                                              : preflightRow.implicitWidth))
                            width: Math.min(activeRowWidth + 12, root.width * 0.9)
                            height: 48
                            z: 6
                            property real highlightOpacity: 0.25
                            property var blurOrigin: {
                                var _x = mapControls.x;
                                var _y = mapControls.y;
                                return mapControls.mapToItem(mapView, 0, 0);
                            }
                            property int buttonHeight: height - 12
                            property bool routeButtonHover: false
                            property bool routeMenuHover: false
                            property bool routeMenuOpen: false
                            property bool routeBridgeHover: false
                            property bool orbitButtonHover: false
                            property bool orbitFlyoutHover: false
                            property bool orbitFlyoutOpen: false

                            function updateRouteMenu() {
                                if (routeButtonHover || routeMenuHover || routeBridgeHover) {
                                    routeMenuOpen = true;
                                    routeMenuCloseTimer.stop();
                                } else {
                                    if (routeMenuOpen && !routeMenuCloseTimer.running) {
                                        routeMenuCloseTimer.start();
                                    }
                                }
                            }

                            function updateOrbitFlyout() {
                                if (orbitButtonHover || orbitFlyoutHover) {
                                    orbitFlyoutOpen = true;
                                    orbitFlyoutCloseTimer.stop();
                                } else {
                                    if (orbitFlyoutOpen && !orbitFlyoutCloseTimer.running) {
                                        orbitFlyoutCloseTimer.start();
                                    }
                                }
                            }

                            Timer {
                                id: routeMenuCloseTimer
                                interval: 500
                                repeat: false
                                onTriggered: mapControls.routeMenuOpen = false
                            }

                            Timer {
                                id: orbitFlyoutCloseTimer
                                interval: 220
                                repeat: false
                                onTriggered: mapControls.orbitFlyoutOpen = false
                            }

                            ShaderEffectSource {
                                id: mapSlice
                                anchors.fill: parent
                                sourceItem: root.currentTab === 1 ? mapView : null
                                sourceRect: Qt.rect(mapControls.blurOrigin.x, mapControls.blurOrigin.y, mapControls.width, mapControls.height)
                                recursive: true
                                live: root.currentTab === 1 && root.visible
                                opacity: 0.0 // keep texture alive for blur only
                            }

                            FastBlur {
                                id: mapBlur
                                anchors.fill: parent
                                source: mapSlice
                                radius: 16
                                transparentBorder: true
                                visible: root.currentTab === 1
                                z: -3
                            }

                            OpacityMask {
                                anchors.fill: parent
                                source: mapBlur
                                maskSource: Rectangle {
                                    width: mapControls.width
                                    height: mapControls.height
                                    radius: height / 2
                                }
                                z: -2
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: height / 2
                                color: Qt.rgba(0.08, 0.08, 0.08, 0.35)
                                border.color: Qt.rgba(1, 1, 1, 0.16)
                                border.width: 1
                                z: -1
                            }

                            Rectangle {
                                anchors.fill: parent
                                radius: height / 2
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.10) }
                                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                                }
                                opacity: mapControls.highlightOpacity
                                Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                z: -0.5
                            }

                            Component {
                                id: batteryChip
                                Item {
                                    property string label: (root.isInFlight && hasApp)
                                                           ? app.currentBatteryText
                                                           : (hasApp ? app.routeBatteryRemainingText : "Remaining: --")
                                    property bool warning: hasApp ? app.routeBatteryWarning : false
                                    implicitWidth: batteryText.implicitWidth + 20
                                    implicitHeight: mapControls.buttonHeight
                                    width: implicitWidth
                                    height: mapControls.buttonHeight

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: height / 2
                                        color: Qt.rgba(0.12, 0.12, 0.12, 0.55)
                                        border.color: warning ? "#ff7b7b" : Qt.rgba(1, 1, 1, 0.12)
                                        border.width: 1
                                    }

                                    Text {
                                        id: batteryText
                                        anchors.centerIn: parent
                                        text: label
                                        color: warning ? "#ff7b7b" : textMuted
                                        font.pixelSize: 12
                                        font.family: "Inter"
                                    }
                                }
                            }

                            Row {
                                id: preflightRow
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 6
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: (isPreflight || isReady) ? 1 : 0
                                visible: opacity > 0.02
                                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                                Component {
                                    id: glassButton
                                    Item {
                                        id: glassButtonRoot
                                        property string label
                                        property var action
                                        property int minWidth: 96
                                        property real targetScale: 1.0
                                        property bool hovered: false
                                        property bool pressed: false
                                        property bool enabled: true
                                        property bool openOnHover: false
                                        property var hoverAction
                                        implicitWidth: Math.max(minWidth, labelText.implicitWidth + 28)
                                        width: implicitWidth
                                        height: mapControls.buttonHeight
                                        scale: targetScale
                                        Behavior on scale { SpringAnimation { spring: 4; damping: 0.38 } }

                                        Rectangle {
                                            anchors.fill: parent
                                            radius: glassBar.radius - 8
                                            color: !enabled ? "transparent"
                                                            : (pressed ? Qt.rgba(0.20, 0.20, 0.20, 0.55)
                                                                       : (hovered ? Qt.rgba(0.16, 0.16, 0.16, 0.35)
                                                                                  : "transparent"))
                                            border.color: "transparent"
                                            Behavior on color { ColorAnimation { duration: 140 } }
                                        }

                                        Text {
                                            id: labelText
                                            anchors.centerIn: parent
                                            text: label
                                            color: !enabled ? textMuted : ((glassButtonRoot.hovered || glassButtonRoot.pressed) ? "#7bc6ff" : textPrimary)
                                            font.pixelSize: 13
                                            font.family: "Inter"
                                            font.bold: (glassButtonRoot.hovered || glassButtonRoot.pressed) && enabled
                                            Behavior on color { ColorAnimation { duration: 120 } }
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            enabled: parent.enabled
                                            hoverEnabled: parent.enabled
                                            onEntered: {
                                                glassButtonRoot.hovered = true;
                                                mapControls.highlightOpacity = glassButtonRoot.pressed ? 0.34 : 0.30;
                                                if (openOnHover && hoverAction) hoverAction(true);
                                            }
                                            onExited: {
                                                glassButtonRoot.hovered = false;
                                                mapControls.highlightOpacity = 0.25;
                                                if (openOnHover && hoverAction) hoverAction(false);
                                            }
                                            onPressed: { glassButtonRoot.pressed = true; targetScale = 0.97; mapControls.highlightOpacity = 0.34 }
                                            onCanceled: { glassButtonRoot.pressed = false; targetScale = 1.0; mapControls.highlightOpacity = glassButtonRoot.hovered ? 0.30 : 0.25 }
                                            onReleased: {
                                                if (glassButtonRoot.pressed && containsMouse && action) action();
                                                glassButtonRoot.pressed = false;
                                                targetScale = 1.0;
                                                mapControls.highlightOpacity = glassButtonRoot.hovered ? 0.30 : 0.25;
                                            }
                                        }
                                    }
                                }

                                Loader {
                                    id: routeMenuButton
                                    active: isPreflight || isReady
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Route"
                                        item.minWidth = 104
                                        item.openOnHover = true
                                        item.hoverAction = function(isHover) {
                                            mapControls.routeButtonHover = isHover;
                                            mapControls.updateRouteMenu();
                                        }
                                        item.action = null
                                    }
                                }
                                Loader {
                                    active: isPreflight || isReady
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Confirm plan"
                                        item.minWidth = 122
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canConfirmPlan : false; })
                                        item.action = function() { requestConfirmPlan(); }
                                    }
                                }
                                Loader {
                                    active: isPreflight || isReady
                                    sourceComponent: batteryChip
                                }
                            }

                            Item {
                                id: routeMenu
                                opacity: mapControls.routeMenuOpen ? 1 : 0
                                scale: mapControls.routeMenuOpen ? 1.0 : 0.98
                                visible: (opacity > 0.02) && (isPreflight || isReady)
                                width: Math.max(180, routeMenuButton.width)
                                height: routeMenuColumn.implicitHeight + 12
                                x: routeMenuButton.x + preflightRow.x
                                y: preflightRow.y + preflightRow.height + 6
                                z: 8
                                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }

                                HoverHandler {
                                    onHoveredChanged: {
                                        mapControls.routeMenuHover = hovered;
                                        mapControls.updateRouteMenu();
                                    }
                                }

                                ShaderEffectSource {
                                    id: routeMenuSlice
                                    anchors.fill: parent
                                    sourceItem: mapView
                                    sourceRect: Qt.rect(routeMenu.x, routeMenu.y, routeMenu.width, routeMenu.height)
                                    recursive: true
                                    live: root.currentTab === 1 && root.visible
                                    visible: false
                                }

                                FastBlur {
                                    id: routeMenuBlur
                                    anchors.fill: parent
                                    source: routeMenuSlice
                                    radius: 20
                                    transparentBorder: true
                                    visible: root.currentTab === 1
                                    z: -3
                                }

                                OpacityMask {
                                    anchors.fill: parent
                                    source: routeMenuBlur
                                    maskSource: Rectangle {
                                        width: routeMenu.width
                                        height: routeMenu.height
                                        radius: 12
                                    }
                                    z: -2
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 12
                                    color: mapGlassFillStrong
                                    border.color: mapGlassBorder
                                    border.width: 1
                                    z: -1
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 12
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                                    }
                                    opacity: 0.22
                                }

                                Column {
                                    id: routeMenuColumn
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 2

                                    Component {
                                        id: routeMenuItem
                                        Item {
                                            property string label
                                            property var action
                                            width: routeMenu.width - 12
                                            height: 30
                                            property bool hovered: false

                                            Rectangle {
                                                anchors.fill: parent
                                                radius: 10
                                                color: hovered ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                                            }

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                anchors.left: parent.left
                                                anchors.leftMargin: 10
                                                text: label
                                                color: hovered ? "#7bc6ff" : textPrimary
                                                font.pixelSize: 12
                                                font.family: "Inter"
                                                scale: hovered ? 1.04 : 1.0
                                                transformOrigin: Item.Left
                                                Behavior on color { ColorAnimation { duration: 120 } }
                                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                onEntered: hovered = true
                                                onExited: hovered = false
                                                onClicked: {
                                                    if (action) action();
                                                    mapControls.routeMenuOpen = false;
                                                }
                                            }
                                        }
                                    }

                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = "Refresh"
                                            item.action = function() { if (hasApp) app.regenerateMap(); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = "Save QGC"
                                            item.action = function() { if (hasApp) app.savePlan(); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = "Import GeoJSON"
                                            item.action = function() { geojsonDialog.open(); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = "Import KML"
                                            item.action = function() { kmlDialog.open(); }
                                        }
                                    }
                                    Rectangle {
                                        width: routeMenu.width - 20
                                        height: 1
                                        color: Qt.rgba(1, 1, 1, 0.12)
                                        anchors.horizontalCenter: parent.horizontalCenter
                                        anchors.topMargin: 4
                                        anchors.bottomMargin: 4
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = Qt.binding(function() {
                                                return hasApp && app.currentBackend === "unreal"
                                                    ? "[*] Unreal (sim)"
                                                    : "[ ] Unreal (sim)";
                                            })
                                            item.action = function() { if (hasApp) app.setBackend("unreal"); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = Qt.binding(function() {
                                                return hasApp && app.currentBackend === "mavlink"
                                                    ? "[*] MAVLink"
                                                    : "[ ] MAVLink";
                                            })
                                            item.action = function() { if (hasApp) app.setBackend("mavlink"); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = Qt.binding(function() {
                                                return hasApp && app.currentBackend === "stub"
                                                    ? "[*] Stub"
                                                    : "[ ] Stub";
                                            })
                                            item.action = function() { if (hasApp) app.setBackend("stub"); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: routeMenuItem
                                        onLoaded: {
                                            item.label = Qt.binding(function() {
                                                return hasApp && app.currentBackend === "custom"
                                                    ? "[*] Custom SDK"
                                                    : "[ ] Custom SDK";
                                            })
                                            item.action = function() { if (hasApp) app.setBackend("custom"); }
                                        }
                                    }
                                }
                            }

                            Item {
                                id: routeHoverBridge
                                visible: mapControls.routeMenuOpen && (isPreflight || isReady)
                                width: routeMenu.width
                                height: Math.max(6, routeMenu.y - (preflightRow.y + preflightRow.height))
                                x: routeMenu.x
                                y: preflightRow.y + preflightRow.height
                                z: 7

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onEntered: {
                                        mapControls.routeBridgeHover = true;
                                        mapControls.updateRouteMenu();
                                    }
                                    onExited: {
                                        mapControls.routeBridgeHover = false;
                                        mapControls.updateRouteMenu();
                                    }
                                }
                            }

                            Row {
                                id: flightRow
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 6
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: isInFlight ? 1 : 0
                                visible: opacity > 0.02
                                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                                Loader {
                                    active: isInFlight
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Edit route"
                                        item.minWidth = 108
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canEditRoute : false; })
                                        item.action = function() { if (hasApp) app.editRoute(); }
                                    }
                                }
                                Loader {
                                    active: isInFlight && hasApp && app.routeEditMode
                                    visible: active
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Apply"
                                        item.minWidth = 86
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canApplyRouteEdits : false; })
                                        item.action = function() { if (hasApp) app.applyRouteEdits(); }
                                    }
                                }
                                Loader {
                                    active: isInFlight && hasApp && app.routeEditMode
                                    visible: active
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Cancel"
                                        item.minWidth = 86
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canCancelRouteEdits : false; })
                                        item.action = function() { if (hasApp) app.cancelRouteEdits(); }
                                    }
                                }
                                Item {
                                    id: orbitButtonGroup
                                    height: mapControls.buttonHeight
                                    implicitWidth: orbitPrimary.implicitWidth + orbitFlyoutWrap.width + (orbitFlyoutWrap.width > 0 ? 6 : 0)

                                    Row {
                                        anchors.fill: parent
                                        spacing: 6

                                        Loader {
                                            id: orbitPrimary
                                            active: isInFlight
                                            sourceComponent: glassButton
                                            onLoaded: {
                                                item.label = "Orbit target"
                                                item.minWidth = 120
                                                item.enabled = Qt.binding(function() { return hasApp ? app.canOpenOrbit : false; })
                                                item.openOnHover = true
                                                item.hoverAction = function(isHover) {
                                                    mapControls.orbitButtonHover = isHover;
                                                    mapControls.updateOrbitFlyout();
                                                }
                                                item.action = function() { requestOrbit(); }
                                            }
                                        }

                                        Item {
                                            id: orbitFlyoutWrap
                                            height: mapControls.buttonHeight
                                            width: mapControls.orbitFlyoutOpen ? orbitAllTargets.implicitWidth : 0
                                            visible: width > 0
                                            opacity: mapControls.orbitFlyoutOpen ? 1.0 : 0.0
                                            scale: mapControls.orbitFlyoutOpen ? 1.0 : 0.96
                                            Behavior on width { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }
                                            Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                            Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }

                                            Loader {
                                                id: orbitAllTargets
                                                active: isInFlight
                                                sourceComponent: glassButton
                                                anchors.verticalCenter: parent.verticalCenter
                                                onLoaded: {
                                                    item.label = "Orbit all targets"
                                                    item.minWidth = 150
                                                    item.enabled = Qt.binding(function() {
                                                        return hasApp ? app.canOpenOrbit : false;
                                                    })
                                                    item.openOnHover = true
                                                    item.hoverAction = function(isHover) {
                                                        mapControls.orbitFlyoutHover = isHover;
                                                        mapControls.updateOrbitFlyout();
                                                    }
                                                    item.action = function() {
                                                        if (!hasApp) return;
                                                        var ids = [];
                                                        var objects = app.confirmedObjects;
                                                        for (var i = 0; i < objects.length; i++) {
                                                            ids.push(objects[i].object_id);
                                                        }
                                                        app.orbitSelectedObjects(ids);
                                                    }
                                                }

                                            }
                                        }
                                    }
                                }
                                Loader {
                                    active: isInFlight
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Return to base"
                                        item.minWidth = 116
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canRtl : false; })
                                        item.action = function() { if (hasApp) app.returnToHome(); }
                                    }
                                }
                                Loader {
                                    active: isInFlight
                                    sourceComponent: batteryChip
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: hasApp && !app.flightCommandsEnabled
                                    text: "Commands disabled"
                                    color: textMuted
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                }
                            }

                            Row {
                                id: rtlRow
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 6
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: isRtl ? 1 : 0
                                visible: opacity > 0.02
                                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                                Loader {
                                    active: isRtl
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Send RTL route"
                                        item.minWidth = 130
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canSendRtlRoute : false; })
                                        item.action = function() { if (hasApp) app.sendRtlRoute(); }
                                    }
                                }
                                Loader {
                                    active: isRtl
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Land complete"
                                        item.minWidth = 118
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canCompleteLanding : false; })
                                        item.action = function() { if (hasApp) app.completeLanding(); }
                                    }
                                }
                                Loader {
                                    active: isRtl
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Abort"
                                        item.minWidth = 86
                                        item.enabled = Qt.binding(function() { return hasApp ? app.canAbortToPreflight : false; })
                                        item.action = function() { if (hasApp) app.abortToPreflight(); }
                                    }
                                }
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: "Returning to home"
                                    color: textMuted
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                }
                            }

                            Row {
                                id: postflightRow
                                anchors.fill: parent
                                anchors.margins: 6
                                spacing: 12
                                anchors.verticalCenter: parent.verticalCenter
                                opacity: isPostflight ? 1 : 0
                                visible: opacity > 0.02
                                Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        text: "Duration: " + (hasApp ? app.flightSummaryDuration : "0s")
                                        color: textPrimary
                                        font.pixelSize: 12
                                        font.family: "Inter"
                                    }
                                    Text {
                                        text: "Distance: " + (hasApp ? app.flightSummaryDistance : "0 m")
                                        color: textMuted
                                        font.pixelSize: 11
                                        font.family: "Inter"
                                    }
                                }
                                Column {
                                    anchors.verticalCenter: parent.verticalCenter
                                    spacing: 2
                                    Text {
                                        text: "Min battery: " + (hasApp ? app.flightSummaryMinBattery : "n/a")
                                        color: textPrimary
                                        font.pixelSize: 12
                                        font.family: "Inter"
                                    }
                                    Text {
                                        text: "Objects: " + (hasApp ? app.flightSummaryObjects : 0)
                                        color: textMuted
                                        font.pixelSize: 11
                                        font.family: "Inter"
                                    }
                                }
                                Loader {
                                    active: isPostflight
                                    sourceComponent: glassButton
                                    onLoaded: {
                                        item.label = "Back to planning"
                                        item.minWidth = 138
                                        item.action = function() { if (hasApp) app.backToPlanning(); }
                                    }
                                }
                            }
                        }

                        Item {
                            id: mapHud
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.leftMargin: 12
                            anchors.topMargin: 12
                            width: mapHudColumn.implicitWidth
                            height: mapHudColumn.implicitHeight
                            z: 7
                            property bool toolsButtonHover: false
                            property bool toolsMenuHover: false
                            property bool toolsBridgeHover: false
                            property bool toolsMenuOpen: false

                            function updateToolsMenu() {
                                if (toolsButtonHover || toolsMenuHover || toolsBridgeHover) {
                                    toolsMenuOpen = true;
                                    toolsMenuCloseTimer.stop();
                                } else {
                                    if (toolsMenuOpen && !toolsMenuCloseTimer.running) {
                                        toolsMenuCloseTimer.start();
                                    }
                                }
                            }

                            function runTool(name, arg) {
                                if (!mapView) return;
                                var callArg = (arg === undefined) ? "" : JSON.stringify(arg);
                                var js = "window.__mapTools && window.__mapTools." + name
                                       + " && window.__mapTools." + name + "(" + callArg + ")";
                                mapView.runJavaScript(js);
                            }

                            Timer {
                                id: toolsMenuCloseTimer
                                interval: 500
                                repeat: false
                                onTriggered: mapHud.toolsMenuOpen = false
                            }

                            Component {
                                id: mapIconButton
                                Item {
                                    id: mapIconButtonRoot
                                    property string icon: "plus"
                                    property var action
                                    property var hoverAction
                                    property bool hovered: false
                                    property bool pressed: false
                                    property real targetScale: 1.0
                                    implicitWidth: 30
                                    implicitHeight: 30
                                    width: parent && parent.width > 0 ? parent.width : implicitWidth
                                    height: parent && parent.height > 0 ? parent.height : implicitHeight
                                    scale: targetScale
                                    Behavior on scale { SpringAnimation { spring: 4; damping: 0.38 } }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 10
                                        color: pressed ? Qt.rgba(0.20, 0.20, 0.20, 0.55)
                                                      : (hovered ? Qt.rgba(0.16, 0.16, 0.16, 0.35)
                                                                 : "transparent")
                                        border.color: "transparent"
                                        Behavior on color { ColorAnimation { duration: 140 } }
                                    }

                                    Item {
                                        anchors.centerIn: parent
                                        width: 16
                                        height: 16

                                        Rectangle {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 12
                                            height: 2
                                            radius: 1
                                            color: hovered || pressed ? "#7bc6ff" : textPrimary
                                            visible: icon === "plus" || icon === "minus"
                                        }
                                        Rectangle {
                                            anchors.horizontalCenter: parent.horizontalCenter
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 2
                                            height: 12
                                            radius: 1
                                            color: hovered || pressed ? "#7bc6ff" : textPrimary
                                            visible: icon === "plus"
                                        }
                                        Rectangle {
                                            id: toolLine
                                            anchors.left: parent.left
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 12
                                            height: 2
                                            radius: 1
                                            color: hovered || pressed ? "#7bc6ff" : textPrimary
                                            visible: icon === "tools"
                                        }
                                        Rectangle {
                                            anchors.left: toolLine.right
                                            anchors.leftMargin: -2
                                            anchors.verticalCenter: parent.verticalCenter
                                            width: 6
                                            height: 6
                                            radius: 3
                                            color: hovered || pressed ? "#7bc6ff" : textPrimary
                                            visible: icon === "tools"
                                        }
                                    }

                                    MouseArea {
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        onEntered: {
                                            hovered = true;
                                            targetScale = 1.03;
                                            if (hoverAction) hoverAction(true);
                                        }
                                        onExited: {
                                            hovered = false;
                                            targetScale = 1.0;
                                            if (hoverAction) hoverAction(false);
                                        }
                                        onPressed: {
                                            mapIconButtonRoot.pressed = true;
                                            targetScale = 0.96;
                                        }
                                        onReleased: {
                                            if (mapIconButtonRoot.pressed && containsMouse && action) action();
                                            mapIconButtonRoot.pressed = false;
                                            targetScale = hovered ? 1.03 : 1.0;
                                        }
                                    }
                                }
                            }

                            Column {
                                id: mapHudColumn
                                spacing: 8

                                Item {
                                    id: zoomCapsule
                                    width: 42
                                    height: 78
                                    property real highlightOpacity: 0.24
                                    property var blurOrigin: {
                                        var _x = zoomCapsule.x;
                                        var _y = zoomCapsule.y;
                                        return zoomCapsule.mapToItem(mapView, 0, 0);
                                    }

                                    ShaderEffectSource {
                                        id: zoomSlice
                                        anchors.fill: parent
                                        sourceItem: mapView
                                        sourceRect: Qt.rect(zoomCapsule.blurOrigin.x, zoomCapsule.blurOrigin.y, zoomCapsule.width, zoomCapsule.height)
                                        recursive: true
                                        live: true
                                        opacity: 0.0
                                    }

                                    FastBlur {
                                        id: zoomBlur
                                        anchors.fill: parent
                                        source: zoomSlice
                                        radius: 16
                                        transparentBorder: true
                                        z: -3
                                    }

                                    OpacityMask {
                                        anchors.fill: parent
                                        source: zoomBlur
                                        maskSource: Rectangle {
                                            width: zoomCapsule.width
                                            height: zoomCapsule.height
                                            radius: 12
                                        }
                                        z: -2
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 12
                                        color: mapGlassFill
                                        border.color: mapGlassBorder
                                        border.width: 1
                                        z: -1
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 12
                                        gradient: Gradient {
                                            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.10) }
                                            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                                        }
                                        opacity: zoomCapsule.highlightOpacity
                                        Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                        z: -0.5
                                    }

                                    Column {
                                        anchors.fill: parent
                                        anchors.margins: 6
                                        spacing: 6

                                        Loader {
                                            width: zoomCapsule.width - 12
                                            height: zoomCapsule.width - 12
                                            sourceComponent: mapIconButton
                                            onLoaded: {
                                                item.icon = "plus"
                                                item.action = function() { mapHud.runTool("zoomIn"); }
                                            }
                                        }
                                        Loader {
                                            width: zoomCapsule.width - 12
                                            height: zoomCapsule.width - 12
                                            sourceComponent: mapIconButton
                                            onLoaded: {
                                                item.icon = "minus"
                                                item.action = function() { mapHud.runTool("zoomOut"); }
                                            }
                                        }
                                    }
                                }

                                Item {
                                    id: toolsCapsule
                                    width: 42
                                    height: 42
                                    property real highlightOpacity: 0.24
                                    property var blurOrigin: {
                                        var _x = toolsCapsule.x;
                                        var _y = toolsCapsule.y;
                                        return toolsCapsule.mapToItem(mapView, 0, 0);
                                    }

                                    ShaderEffectSource {
                                        id: toolsSlice
                                        anchors.fill: parent
                                        sourceItem: mapView
                                        sourceRect: Qt.rect(toolsCapsule.blurOrigin.x, toolsCapsule.blurOrigin.y, toolsCapsule.width, toolsCapsule.height)
                                        recursive: true
                                        live: true
                                        opacity: 0.0
                                    }

                                    FastBlur {
                                        id: toolsBlur
                                        anchors.fill: parent
                                        source: toolsSlice
                                        radius: 16
                                        transparentBorder: true
                                        z: -3
                                    }

                                    OpacityMask {
                                        anchors.fill: parent
                                        source: toolsBlur
                                        maskSource: Rectangle {
                                            width: toolsCapsule.width
                                            height: toolsCapsule.height
                                            radius: 12
                                        }
                                        z: -2
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 12
                                        color: mapGlassFill
                                        border.color: mapGlassBorder
                                        border.width: 1
                                        z: -1
                                    }

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: 12
                                        gradient: Gradient {
                                            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.10) }
                                            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                                        }
                                        opacity: toolsCapsule.highlightOpacity
                                        Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                        z: -0.5
                                    }

                                    Loader {
                                        anchors.fill: parent
                                        width: toolsCapsule.width - 12
                                        height: toolsCapsule.width - 12
                                        sourceComponent: mapIconButton
                                        onLoaded: {
                                            item.icon = "tools"
                                            item.hoverAction = function(isHover) {
                                                mapHud.toolsButtonHover = isHover;
                                                mapHud.updateToolsMenu();
                                            }
                                            item.action = null
                                        }
                                    }
                                }
                            }

                            Item {
                                id: toolsMenu
                                opacity: mapHud.toolsMenuOpen ? 1 : 0
                                scale: mapHud.toolsMenuOpen ? 1.0 : 0.98
                                visible: opacity > 0.02
                                width: 190
                                height: toolsMenuColumn.implicitHeight + 12
                                x: toolsCapsule.x + toolsCapsule.width + 8
                                y: toolsCapsule.y - 4
                                z: 8
                                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }

                                HoverHandler {
                                    onHoveredChanged: {
                                        mapHud.toolsMenuHover = hovered;
                                        mapHud.updateToolsMenu();
                                    }
                                }

                                ShaderEffectSource {
                                    id: toolsMenuSlice
                                    anchors.fill: parent
                                    sourceItem: mapView
                                    sourceRect: Qt.rect(toolsMenu.x, toolsMenu.y, toolsMenu.width, toolsMenu.height)
                                    recursive: true
                                    live: root.currentTab === 1 && root.visible
                                    visible: false
                                }

                                FastBlur {
                                    id: toolsMenuBlur
                                    anchors.fill: parent
                                    source: toolsMenuSlice
                                    radius: 20
                                    transparentBorder: true
                                    visible: root.currentTab === 1
                                    z: -3
                                }

                                OpacityMask {
                                    anchors.fill: parent
                                    source: toolsMenuBlur
                                    maskSource: Rectangle {
                                        width: toolsMenu.width
                                        height: toolsMenu.height
                                        radius: 12
                                    }
                                    z: -2
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 12
                                    color: mapGlassFillStrong
                                    border.color: mapGlassBorder
                                    border.width: 1
                                    z: -1
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 12
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                                    }
                                    opacity: 0.22
                                }

                                Column {
                                    id: toolsMenuColumn
                                    anchors.fill: parent
                                    anchors.margins: 6
                                    spacing: 2

                                    Component {
                                        id: toolsMenuItem
                                        Item {
                                            property string label
                                            property var action
                                            width: toolsMenu.width - 12
                                            height: 30
                                            property bool hovered: false

                                            Rectangle {
                                                anchors.fill: parent
                                                radius: 10
                                                color: hovered ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                                            }

                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                anchors.left: parent.left
                                                anchors.leftMargin: 10
                                                text: label
                                                color: hovered ? "#7bc6ff" : textPrimary
                                                font.pixelSize: 12
                                                font.family: "Inter"
                                                scale: hovered ? 1.04 : 1.0
                                                transformOrigin: Item.Left
                                                Behavior on color { ColorAnimation { duration: 120 } }
                                                Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
                                            }

                                            MouseArea {
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                onEntered: hovered = true
                                                onExited: hovered = false
                                                onClicked: {
                                                    if (action) action();
                                                    mapHud.toolsMenuOpen = false;
                                                }
                                            }
                                        }
                                    }

                                    Loader {
                                        sourceComponent: toolsMenuItem
                                        onLoaded: {
                                            item.label = "Draw path"
                                            item.action = function() { mapHud.runTool("drawPath"); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: toolsMenuItem
                                        onLoaded: {
                                            item.label = "Remove"
                                            item.action = function() { mapHud.runTool("setRemoveMode", true); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: toolsMenuItem
                                        active: root.isPreflight || root.isReady
                                        onLoaded: {
                                            item.label = "Set home"
                                            item.action = function() { if (hasApp) app.startHomePickMode(); }
                                        }
                                    }
                                    Loader {
                                        sourceComponent: toolsMenuItem
                                        onLoaded: {
                                            item.label = "Reset view"
                                            item.action = function() { mapHud.runTool("resetView"); }
                                        }
                                    }
                                }
                            }

                            Item {
                                id: toolsHoverBridge
                                visible: mapHud.toolsMenuOpen
                                width: Math.max(6, toolsMenu.x - (toolsCapsule.x + toolsCapsule.width))
                                height: toolsMenu.height
                                x: toolsCapsule.x + toolsCapsule.width
                                y: toolsMenu.y
                                z: 7

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onEntered: {
                                        mapHud.toolsBridgeHover = true;
                                        mapHud.updateToolsMenu();
                                    }
                                    onExited: {
                                        mapHud.toolsBridgeHover = false;
                                        mapHud.updateToolsMenu();
                                    }
                                }
                            }
                        }

                        Item {
                            id: autoOrbitDock
                            anchors.horizontalCenter: mapControls.horizontalCenter
                            anchors.top: mapControls.bottom
                            anchors.topMargin: 8
                            width: autoOrbitMenu.width
                            height: autoOrbitTrigger.height + autoOrbitMenu.height + 10
                            visible: currentTab === 1
                            z: 6
                            property bool triggerHover: false
                            property bool menuHover: false
                            property bool bridgeHover: false
                            property bool menuOpen: triggerHover || menuHover || bridgeHover

                            Item {
                                id: autoOrbitTrigger
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.top: parent.top
                                width: 148
                                height: 38
                                scale: autoOrbitTriggerMouse.pressed ? 0.97 : 1.0
                                Behavior on scale { SpringAnimation { spring: 4; damping: 0.38 } }

                                ShaderEffectSource {
                                    id: autoOrbitTriggerSlice
                                    anchors.fill: parent
                                    sourceItem: mapView
                                    sourceRect: Qt.rect(autoOrbitDock.x + autoOrbitTrigger.x,
                                                        autoOrbitDock.y + autoOrbitTrigger.y,
                                                        autoOrbitTrigger.width,
                                                        autoOrbitTrigger.height)
                                    recursive: true
                                    live: root.currentTab === 1 && root.visible
                                    visible: false
                                }

                                FastBlur {
                                    id: autoOrbitTriggerBlur
                                    anchors.fill: parent
                                    source: autoOrbitTriggerSlice
                                    radius: 16
                                    transparentBorder: true
                                    visible: root.currentTab === 1
                                    z: -3
                                }

                                OpacityMask {
                                    anchors.fill: parent
                                    source: autoOrbitTriggerBlur
                                    maskSource: Rectangle {
                                        width: autoOrbitTrigger.width
                                        height: autoOrbitTrigger.height
                                        radius: height / 2
                                    }
                                    z: -2
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: height / 2
                                    color: mapGlassFill
                                    border.color: mapGlassBorder
                                    border.width: 1
                                    z: -1
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: height / 2
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                                    }
                                    opacity: autoOrbitDock.menuOpen ? 0.32 : 0.22
                                    Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                }

                                Row {
                                    anchors.fill: parent
                                    anchors.leftMargin: 14
                                    anchors.rightMargin: 14
                                    spacing: 8

                                    Rectangle {
                                        width: 10
                                        height: 10
                                        radius: 5
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: hasApp && app.autoOrbitEnabled ? "#67e8a9" : Qt.rgba(1, 1, 1, 0.32)
                                        border.color: Qt.rgba(1, 1, 1, 0.2)
                                    }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: "Auto orbit"
                                        color: textPrimary
                                        font.pixelSize: 13
                                        font.family: "Inter"
                                        font.bold: hasApp ? app.autoOrbitEnabled : false
                                    }

                                    Item { width: 1; height: 1; anchors.verticalCenter: parent.verticalCenter }

                                    Text {
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: Math.round(hasApp ? app.orbitRadiusM : 50) + " m"
                                        color: hasApp && app.autoOrbitEnabled ? textPrimary : textMuted
                                        font.pixelSize: 11
                                        font.family: "Inter"
                                    }
                                }

                                MouseArea {
                                    id: autoOrbitTriggerMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onEntered: {
                                        autoOrbitDock.triggerHover = true;
                                    }
                                    onExited: {
                                        autoOrbitDock.triggerHover = false;
                                    }
                                    onClicked: {
                                        if (hasApp) app.setAutoOrbitEnabled(!app.autoOrbitEnabled);
                                    }
                                }
                            }

                            Item {
                                id: autoOrbitHoverBridge
                                anchors.top: autoOrbitTrigger.bottom
                                anchors.horizontalCenter: autoOrbitTrigger.horizontalCenter
                                width: autoOrbitTrigger.width
                                height: autoOrbitDock.menuOpen ? 8 : 0
                                visible: autoOrbitDock.menuOpen

                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    onEntered: autoOrbitDock.bridgeHover = true
                                    onExited: autoOrbitDock.bridgeHover = false
                                }
                            }

                            Item {
                                id: autoOrbitMenu
                                anchors.horizontalCenter: autoOrbitTrigger.horizontalCenter
                                anchors.top: autoOrbitHoverBridge.bottom
                                width: Math.min(252, root.width * 0.42)
                                height: autoOrbitMenuColumn.implicitHeight + 14
                                visible: opacity > 0.02
                                opacity: autoOrbitDock.menuOpen ? 1 : 0
                                scale: autoOrbitDock.menuOpen ? 1.0 : 0.96
                                clip: true
                                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutQuad } }

                                ShaderEffectSource {
                                    id: autoOrbitMenuSlice
                                    anchors.fill: parent
                                    sourceItem: mapView
                                    sourceRect: Qt.rect(autoOrbitDock.x + autoOrbitMenu.x,
                                                        autoOrbitDock.y + autoOrbitMenu.y,
                                                        autoOrbitMenu.width,
                                                        autoOrbitMenu.height)
                                    recursive: true
                                    live: root.currentTab === 1 && root.visible
                                    visible: false
                                }

                                FastBlur {
                                    id: autoOrbitMenuBlur
                                    anchors.fill: parent
                                    source: autoOrbitMenuSlice
                                    radius: 18
                                    transparentBorder: true
                                    visible: root.currentTab === 1
                                    z: -3
                                }

                                OpacityMask {
                                    anchors.fill: parent
                                    source: autoOrbitMenuBlur
                                    maskSource: Rectangle {
                                        width: autoOrbitMenu.width
                                        height: autoOrbitMenu.height
                                        radius: 16
                                    }
                                    z: -2
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 16
                                    color: mapGlassFillStrong
                                    border.color: mapGlassBorder
                                    border.width: 1
                                    z: -1
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 16
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                                    }
                                    opacity: 0.26
                                }

                                HoverHandler {
                                    onHoveredChanged: {
                                        autoOrbitDock.menuHover = hovered;
                                    }
                                }

                                ColumnLayout {
                                    id: autoOrbitMenuColumn
                                    anchors.fill: parent
                                    anchors.margins: 10
                                    spacing: 6

                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 8

                                        Text {
                                            text: "Radius"
                                            color: textMuted
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                            Layout.alignment: Qt.AlignVCenter
                                        }

                                        Slider {
                                            id: orbitRadiusSlider
                                            from: 10
                                            to: 150
                                            stepSize: 1
                                            value: hasApp ? app.orbitRadiusM : 50
                                            enabled: hasApp
                                            live: true
                                            Layout.fillWidth: true
                                            Layout.alignment: Qt.AlignVCenter
                                            onMoved: {
                                                if (hasApp) app.setOrbitRadiusM(value);
                                            }
                                            onPressedChanged: {
                                                if (!pressed && hasApp) app.setOrbitRadiusM(value);
                                            }
                                        }

                                        Text {
                                            text: Math.round(hasApp ? app.orbitRadiusM : orbitRadiusSlider.value) + " m"
                                            color: textPrimary
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                            Layout.alignment: Qt.AlignVCenter
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            anchors.fill: parent
                            radius: cardRadius
                            color: Qt.rgba(0.02, 0.02, 0.02, 0.44)
                            border.color: Qt.rgba(1, 1, 1, 0.08)
                            border.width: 1
                            visible: mapOverlay.text !== ""
                            z: 5
                            Text {
                                id: mapOverlay
                                anchors.centerIn: parent
                                text: "Map loading..."
                                color: textPrimary
                                font.pixelSize: 20
                                font.bold: true
                            }
                        }

                    }
                }

                // Logs
                Item {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Rectangle {
                        anchors.fill: parent
                        radius: cardRadius
                        color: panelColor
                        border.color: borderColor
                        clip: true

                        ListView {
                            id: logView
                            anchors.fill: parent
                            model: hasApp ? app.logs : []
                            delegate: Text {
                                text: modelData
                                color: textPrimary
                                font.pixelSize: 12
                                font.family: "Inter"
                                elide: Text.ElideLeft
                            }
                            onCountChanged: positionViewAtEnd()
                            Connections {
                                target: hasApp ? app : null
                                function onLogsChanged() { logView.positionViewAtEnd(); }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            visible: logView.count === 0
                            text: "No logs yet"
                            color: textMuted
                            font.pixelSize: 16
                            font.bold: true
                            z: 5
                        }
                    }
                }
            }
        }
    }

    // Detection notification capsule with quick navigation shortcuts
    Item {
        id: detectionToast
        anchors.right: parent.right
        anchors.rightMargin: 24
        anchors.verticalCenter: navFloating.verticalCenter
        width: navFloating.width
        height: navFloating.height
        visible: root.toastVisible
        opacity: visible ? 1 : 0
        z: 120

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        ShaderEffectSource {
            id: toastSlice
            anchors.fill: parent
            sourceItem: sceneLayer
            sourceRect: Qt.rect(detectionToast.x, detectionToast.y, detectionToast.width, detectionToast.height)
            recursive: true
            live: true
            visible: false
        }

        FastBlur {
            id: toastBlur
            anchors.fill: parent
            source: toastSlice
            radius: 16
            transparentBorder: true
            z: -3
        }

        OpacityMask {
            anchors.fill: parent
            source: toastBlur
            maskSource: Rectangle {
                width: detectionToast.width
                height: detectionToast.height
                radius: height / 2
            }
            z: -2
        }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: Qt.rgba(0.08, 0.08, 0.08, 0.42)
            border.color: Qt.rgba(1, 1, 1, 0.18)
            border.width: 1
            z: -1
        }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.06) }
            }
            opacity: 0.26
            Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
            z: -0.5
        }

        Column {
            id: toastContent
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            spacing: 2
            width: detectionToast.width - 24

            Text {
                text: root.toastTitle
                color: "#7bc6ff"
                font.pixelSize: 13
                font.family: "Inter"
                font.weight: Font.Medium
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                maximumLineCount: 1
                width: parent.width
            }
            Text {
                text: root.toastMessage
                color: textPrimary
                font.pixelSize: 15
                font.family: "Inter"
                horizontalAlignment: Text.AlignHCenter
                elide: Text.ElideRight
                maximumLineCount: 1
                width: parent.width
            }
        }
    }

    Timer {
        id: toastHideTimer
        interval: 6000
        running: false
        repeat: false
        onTriggered: root.toastVisible = false
    }

    Connections {
        target: hasApp ? app : null
        function onToastRequested(message) {
            root.toastTitle = "Notification"
            root.toastMessage = message
            root.toastVisible = true
            toastHideTimer.restart()
        }
        function onObjectNotificationReceived(objectId, classId, confidence, message, trackId) {
            root.toastTitle = "Detection"
            var idLabel = objectId && objectId.length ? ("#" + objectId) : "n/a";
            var clsLabel = classId >= 0 ? classId : "n/a";
            var confLabel = confidence > 0 ? (confidence * 100).toFixed(1) + "%" : "n/a";
            var trackLabel = (trackId !== null && trackId !== undefined) ? trackId : "n/a";
            root.toastMessage = "Object: " + idLabel + " Track: " + trackLabel + " Class: " + clsLabel + " Conf: " + confLabel + "."
            root.toastVisible = true
            toastHideTimer.restart()
        }
    }

    Item {
        id: confirmPlanSheet
        anchors.fill: parent
        visible: confirmPlanSheetVisible
        opacity: confirmPlanSheetVisible ? 1 : 0
        z: 139

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        Item {
            width: Math.min(parent.width - 48, 480)
            anchors.centerIn: parent
            implicitHeight: confirmPlanColumn.implicitHeight + 44

            ShaderEffectSource {
                id: confirmPlanSlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(parent.x, parent.y, parent.width, parent.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: confirmPlanBlur
                anchors.fill: parent
                source: confirmPlanSlice
                radius: 20
                transparentBorder: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: confirmPlanBlur
                maskSource: Rectangle {
                    width: confirmPlanBlur.width
                    height: confirmPlanBlur.height
                    radius: 24
                }
                z: -2
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                color: Qt.rgba(0.08, 0.08, 0.08, 0.56)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                }
                opacity: 0.22
            }

            ColumnLayout {
                id: confirmPlanColumn
                anchors.fill: parent
                anchors.margins: 22
                spacing: 14

                Text {
                    text: hasApp && app.currentBackend === "unreal" ? "Confirm route and start flight" : "Confirm plan"
                    color: textPrimary
                    font.pixelSize: 20
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp && app.currentBackend === "unreal"
                          ? "The mission route will be accepted and the drone will switch into flight mode immediately."
                          : "Accept the current route and lock it as the active mission plan."
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Cancel"
                            item.action = function() { confirmPlanSheetVisible = false; }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = hasApp && app.currentBackend === "unreal" ? "Confirm and fly" : "Confirm plan"
                            item.accent = true
                            item.action = function() {
                                confirmPlanSheetVisible = false;
                                if (hasApp) app.confirmPlan();
                            }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: routeBatterySheet
        anchors.fill: parent
        visible: hasApp && app.routeBatteryAdvisoryVisible
        opacity: visible ? 1 : 0
        z: 141

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        Item {
            width: Math.min(parent.width - 48, 520)
            anchors.centerIn: parent
            implicitHeight: routeBatteryColumn.implicitHeight + 44

            ShaderEffectSource {
                id: routeBatterySlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(parent.x, parent.y, parent.width, parent.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: routeBatteryBlur
                anchors.fill: parent
                source: routeBatterySlice
                radius: 20
                transparentBorder: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: routeBatteryBlur
                maskSource: Rectangle {
                    width: routeBatteryBlur.width
                    height: routeBatteryBlur.height
                    radius: 24
                }
                z: -2
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                color: Qt.rgba(0.08, 0.08, 0.08, 0.56)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                }
                opacity: 0.22
            }

            ColumnLayout {
                id: routeBatteryColumn
                anchors.fill: parent
                anchors.margins: 22
                spacing: 14

                Text {
                    text: "Route battery warning"
                    color: textPrimary
                    font.pixelSize: 20
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp ? app.routeBatteryAdvisoryText : ""
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Cancel"
                            item.action = function() { if (hasApp) app.respondRouteBatteryAdvisory("cancel"); }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Return home"
                            item.accent = true
                            item.enabled = Qt.binding(function() { return hasApp ? app.routeBatteryReturnHomeAvailable : false; })
                            item.action = function() { if (hasApp) app.respondRouteBatteryAdvisory("rtl"); }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Proceed anyway"
                            item.action = function() { if (hasApp) app.respondRouteBatteryAdvisory("proceed"); }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: orbitBatterySheet
        anchors.fill: parent
        visible: hasApp && app.orbitBatteryAdvisoryVisible
        opacity: visible ? 1 : 0
        z: 142

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        Item {
            width: Math.min(parent.width - 48, 520)
            anchors.centerIn: parent
            implicitHeight: orbitBatteryColumn.implicitHeight + 44

            ShaderEffectSource {
                id: orbitBatterySlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(parent.x, parent.y, parent.width, parent.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: orbitBatteryBlur
                anchors.fill: parent
                source: orbitBatterySlice
                radius: 20
                transparentBorder: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: orbitBatteryBlur
                maskSource: Rectangle {
                    width: orbitBatteryBlur.width
                    height: orbitBatteryBlur.height
                    radius: 24
                }
                z: -2
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                color: Qt.rgba(0.08, 0.08, 0.08, 0.56)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                }
                opacity: 0.22
            }

            ColumnLayout {
                id: orbitBatteryColumn
                anchors.fill: parent
                anchors.margins: 22
                spacing: 14

                Text {
                    text: "Orbit battery warning"
                    color: textPrimary
                    font.pixelSize: 20
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp ? app.orbitBatteryAdvisoryText : ""
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Cancel orbit"
                            item.action = function() { if (hasApp) app.respondOrbitBatteryAdvisory("cancel"); }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Return home"
                            item.accent = true
                            item.enabled = Qt.binding(function() { return hasApp ? app.orbitBatteryReturnHomeAvailable : false; })
                            item.action = function() { if (hasApp) app.respondOrbitBatteryAdvisory("rtl"); }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: overlayActionButton
                        onLoaded: {
                            item.label = "Proceed anyway"
                            item.action = function() { if (hasApp) app.respondOrbitBatteryAdvisory("proceed"); }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: orbitSelectionSheet
        anchors.fill: parent
        visible: orbitSelectionSheetVisible
        opacity: orbitSelectionSheetVisible ? 1 : 0
        z: 140

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.42)
        }

        Item {
            width: Math.min(parent.width - 48, 520)
            height: Math.min(parent.height - 96, 560)
            anchors.centerIn: parent

            ShaderEffectSource {
                id: orbitSheetSlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(parent.x, parent.y, parent.width, parent.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: orbitSheetBlur
                anchors.fill: parent
                source: orbitSheetSlice
                radius: 22
                transparentBorder: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: orbitSheetBlur
                maskSource: Rectangle {
                    width: orbitSelectionCard.width
                    height: orbitSelectionCard.height
                    radius: 26
                }
                z: -2
            }

            Rectangle {
                id: orbitSelectionCard
                anchors.fill: parent
                radius: 26
                color: Qt.rgba(0.08, 0.08, 0.08, 0.54)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: orbitSelectionCard.radius
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                }
                opacity: 0.24
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 14

                Text {
                    text: "Orbit target selection"
                    color: textPrimary
                    font.pixelSize: 22
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: "Pick one or more confirmed targets. The same numbers are shown on the map markers."
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                Component {
                    id: orbitSheetActionButton

                    Item {
                        id: orbitSheetActionButtonRoot
                        property string label
                        property var action
                        property bool accent: false
                        property bool hovered: false
                        property bool pressed: false

                        Layout.fillWidth: true
                        implicitHeight: 44
                        opacity: enabled ? 1.0 : 0.48
                        scale: pressed && enabled ? 0.985 : 1.0
                        Behavior on scale { NumberAnimation { duration: 90; easing.type: Easing.OutQuad } }

                        Rectangle {
                            anchors.fill: parent
                            radius: height / 2
                            color: orbitSheetActionButtonRoot.accent
                                   ? (orbitSheetActionButtonRoot.pressed ? Qt.rgba(0.20, 0.48, 0.78, 0.40)
                                                                         : Qt.rgba(0.12, 0.32, 0.52, 0.28))
                                   : (orbitSheetActionButtonRoot.pressed ? Qt.rgba(1, 1, 1, 0.16)
                                                                         : Qt.rgba(1, 1, 1, 0.09))
                            border.width: 1
                            border.color: orbitSheetActionButtonRoot.accent
                                          ? Qt.rgba(0.62, 0.84, 1, orbitSheetActionButtonRoot.hovered ? 0.54 : 0.36)
                                          : Qt.rgba(1, 1, 1, orbitSheetActionButtonRoot.hovered ? 0.28 : 0.18)
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Behavior on border.color { ColorAnimation { duration: 120 } }
                        }

                        Rectangle {
                            anchors.fill: parent
                            radius: height / 2
                            gradient: Gradient {
                                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, orbitSheetActionButtonRoot.hovered ? 0.20 : 0.14) }
                                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                            }
                        }

                        Text {
                            anchors.centerIn: parent
                            text: orbitSheetActionButtonRoot.label
                            color: orbitSheetActionButtonRoot.accent ? "#dff1ff" : textPrimary
                            font.pixelSize: 13
                            font.family: "Inter"
                            font.bold: orbitSheetActionButtonRoot.hovered || orbitSheetActionButtonRoot.pressed
                        }

                        MouseArea {
                            anchors.fill: parent
                            enabled: orbitSheetActionButtonRoot.enabled
                            hoverEnabled: orbitSheetActionButtonRoot.enabled
                            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                            onEntered: orbitSheetActionButtonRoot.hovered = true
                            onExited: {
                                orbitSheetActionButtonRoot.hovered = false
                                orbitSheetActionButtonRoot.pressed = false
                            }
                            onPressed: orbitSheetActionButtonRoot.pressed = true
                            onCanceled: orbitSheetActionButtonRoot.pressed = false
                            onReleased: {
                                if (orbitSheetActionButtonRoot.pressed && containsMouse && orbitSheetActionButtonRoot.action) {
                                    orbitSheetActionButtonRoot.action()
                                }
                                orbitSheetActionButtonRoot.pressed = false
                            }
                        }
                    }
                }

                ListView {
                    id: orbitList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 10
                    model: hasApp ? app.confirmedObjects : []
                    delegate: Rectangle {
                        property bool selected: orbitSelection.indexOf(modelData.object_id) !== -1
                        property bool hovered: false
                        width: orbitList.width
                        height: 84
                        radius: 18
                        color: selected ? Qt.rgba(1, 1, 1, 0.14) : (hovered ? Qt.rgba(1, 1, 1, 0.08) : Qt.rgba(0.08, 0.08, 0.08, 0.26))
                        border.color: selected ? Qt.rgba(1, 1, 1, 0.24) : Qt.rgba(1, 1, 1, hovered ? 0.16 : 0.10)
                        border.width: 1
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Behavior on border.color { ColorAnimation { duration: 120 } }

                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            color: "transparent"
                            border.width: selected ? 1 : 0
                            border.color: Qt.rgba(0.62, 0.84, 1, 0.28)
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 14
                            spacing: 14

                            Rectangle {
                                width: 34
                                height: 34
                                radius: 17
                                color: "#ffffff"
                                border.color: "#000000"
                                border.width: 2
                                Layout.alignment: Qt.AlignVCenter
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.display_index
                                    color: "#000000"
                                    font.pixelSize: 13
                                    font.family: "Inter"
                                    font.bold: true
                                }
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 4

                                Text {
                                    Layout.fillWidth: true
                                    text: "#" + modelData.object_id
                                    color: textPrimary
                                    font.pixelSize: 14
                                    font.family: "Inter"
                                    font.bold: true
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: "Class " + modelData.class_id + "  Confidence " + (modelData.confidence * 100).toFixed(1) + "%"
                                    color: textMuted
                                    font.pixelSize: 11
                                    font.family: "Inter"
                                    elide: Text.ElideRight
                                }
                                Text {
                                    Layout.fillWidth: true
                                    text: "Lat " + Number(modelData.lat).toFixed(5) + "  Lon " + Number(modelData.lon).toFixed(5)
                                    color: textMuted
                                    font.pixelSize: 11
                                    font.family: "Inter"
                                    elide: Text.ElideRight
                                }
                            }

                            Rectangle {
                                width: 24
                                height: 24
                                radius: 8
                                Layout.alignment: Qt.AlignVCenter
                                color: selected ? "#1581df" : Qt.rgba(1, 1, 1, 0.08)
                                border.width: 1
                                border.color: selected ? Qt.rgba(0.80, 0.92, 1, 0.68) : Qt.rgba(1, 1, 1, 0.24)
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: 10
                                    height: 10
                                    radius: 3
                                    color: "#ffffff"
                                    visible: selected
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    radius: parent.radius
                                    color: "transparent"
                                    border.width: selected ? 1 : 0
                                    border.color: Qt.rgba(1, 1, 1, 0.18)
                                }
                            }
                        }

                        MouseArea {
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onEntered: parent.hovered = true
                            onExited: parent.hovered = false
                            onClicked: {
                                if (hasApp) {
                                    app.selectConfirmedObject(modelData.object_id);
                                }
                                toggleOrbitSelection(modelData.object_id);
                            }
                        }
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: orbitSheetActionButton
                        onLoaded: {
                            item.label = "Cancel"
                            item.action = function() {
                                orbitSelectionSheetVisible = false
                                orbitSelection = []
                            }
                        }
                    }

                    Loader {
                        Layout.fillWidth: true
                        sourceComponent: orbitSheetActionButton
                        onLoaded: {
                            item.label = "Orbit selected"
                            item.accent = true
                            item.enabled = Qt.binding(function() { return orbitSelection.length > 0; })
                            item.action = function() {
                                if (!hasApp) return;
                                app.orbitSelectedObjects(orbitSelection);
                                orbitSelectionSheetVisible = false;
                                orbitSelection = [];
                            }
                        }
                    }
                }
            }
        }
    }

    Item {
        id: recoverableMissionSheet
        anchors.fill: parent
        visible: hasApp && app.recoverableMissionAvailable && app.currentBackend === "unreal" && app.unrealRuntimeStatus !== "disconnected"
        opacity: visible ? 1 : 0
        z: 135

        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutQuad } }

        Rectangle {
            anchors.fill: parent
            color: Qt.rgba(0, 0, 0, 0.22)
        }

        Item {
            width: Math.min(parent.width - 64, 480)
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            anchors.topMargin: 72
            implicitHeight: recoverableMissionColumn.implicitHeight + 28

            ShaderEffectSource {
                id: recoverableMissionSlice
                anchors.fill: parent
                sourceItem: sceneLayer
                sourceRect: Qt.rect(parent.x, parent.y, parent.width, parent.height)
                recursive: true
                live: root.visible
                visible: false
            }

            FastBlur {
                id: recoverableMissionBlur
                anchors.fill: parent
                source: recoverableMissionSlice
                radius: 20
                transparentBorder: true
                z: -3
            }

            OpacityMask {
                anchors.fill: parent
                source: recoverableMissionBlur
                maskSource: Rectangle {
                    width: recoverableMissionBlur.width
                    height: recoverableMissionBlur.height
                    radius: 24
                }
                z: -2
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                color: Qt.rgba(0.08, 0.08, 0.08, 0.56)
                border.color: Qt.rgba(1, 1, 1, 0.18)
                border.width: 1
            }

            Rectangle {
                anchors.fill: parent
                radius: 24
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
                }
                opacity: 0.22
            }

            ColumnLayout {
                id: recoverableMissionColumn
                anchors.fill: parent
                anchors.margins: 18
                spacing: 12

                Text {
                    text: "Unreal session interrupted"
                    color: textPrimary
                    font.pixelSize: 18
                    font.family: "Inter"
                    font.bold: true
                }

                Text {
                    Layout.fillWidth: true
                    text: hasApp ? app.recoverableMissionText : ""
                    color: textMuted
                    font.pixelSize: 12
                    font.family: "Inter"
                    wrapMode: Text.WordWrap
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 10

                    Button {
                        Layout.fillWidth: true
                        text: "Discard"
                        onClicked: if (hasApp) app.discardRecoverableMission()
                    }

                    Button {
                        Layout.fillWidth: true
                        text: "Restore route"
                        onClicked: if (hasApp) app.restoreRecoverableMission()
                    }
                }
            }
        }
    }

    // Floating navigation capsule (unchanged)
    Item {
        id: navFloating
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 52
        width: Math.min(root.width * 0.34, 320)
        height: 48
        z: 50
        property real highlightOpacity: 0.25

        ShaderEffectSource {
            id: navSlice
            anchors.fill: parent
            sourceItem: sceneLayer
            opacity: 0.0 // keep texture alive for blur but don't show raw copy to avoid bleed
            live: true
            recursive: true
            sourceRect: Qt.rect(navFloating.x, navFloating.y, navFloating.width, navFloating.height)
        }

        FastBlur {
            id: navBlur
            anchors.fill: parent
            source: navSlice
            radius: 16
            transparentBorder: true
            z: -3
        }

        OpacityMask {
            anchors.fill: parent
            source: navBlur
            maskSource: Rectangle {
                width: navFloating.width
                height: navFloating.height
                radius: height / 2
            }
            z: -2
        }

        Rectangle {
            id: glassBar
            anchors.fill: parent
            radius: height / 2
            color: Qt.rgba(0.08, 0.08, 0.08, 0.35)
            border.color: Qt.rgba(1, 1, 1, 0.16)
            border.width: 1
        }

        Rectangle {
            id: glassHighlight
            anchors.fill: glassBar
            radius: glassBar.radius
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.06) }
            }
            opacity: navFloating.highlightOpacity
            Behavior on opacity { NumberAnimation { duration: 120; easing.type: Easing.OutQuad } }
        }

        Row {
            id: navRow
            anchors.fill: parent
            anchors.margins: 6
            spacing: 0

            Component {
                id: navSegment
                Item {
                    property string label
                    property int index: 0
                    readonly property bool selected: currentTab === index
                    width: navRow.width / 3
                    height: navRow.height
                    property real targetScale: 1.0
                    scale: targetScale
                    Behavior on scale { SpringAnimation { spring: 4; damping: 0.38 } }

                    Rectangle {
                        anchors.fill: parent
                        radius: glassBar.radius - 8
                        color: selected ? Qt.rgba(0.2, 0.2, 0.2, 0.7) : "transparent"
                        border.color: selected ? Qt.rgba(1, 1, 1, 0.12) : "transparent"
                        Behavior on color { ColorAnimation { duration: 150 } }
                    }

                    Text {
                        anchors.centerIn: parent
                        text: label
                        color: selected ? "#7bc6ff" : textPrimary
                        font.pixelSize: 13
                        font.family: "Inter"
                        font.bold: selected
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        onPressed: {
                            targetScale = 0.97;
                            navFloating.highlightOpacity = 0.32;
                        }
                        onReleased: {
                            targetScale = 1.0;
                            navFloating.highlightOpacity = 0.25;
                        }
                        onCanceled: {
                            targetScale = 1.0;
                            navFloating.highlightOpacity = 0.25;
                        }
                        onClicked: currentTab = index
                    }
                }
            }

            Loader { sourceComponent: navSegment; onLoaded: { item.label = "Detector"; item.index = 0 } }
            Loader { id: plannerTabLoader; sourceComponent: navSegment; onLoaded: { item.label = "Planner";  item.index = 1 } }
            Loader { sourceComponent: navSegment; onLoaded: { item.label = "Logs";     item.index = 2 } }
        }
    }

    Item {
        id: updateMapFloating
        property bool plannerActive: currentTab === 1
        property real lift: 0
        width: Math.max(160, (plannerTabLoader.item ? plannerTabLoader.item.width + 72 : 180))
        height: 38
        anchors.horizontalCenter: navFloating.horizontalCenter
        anchors.bottom: navFloating.top
        anchors.bottomMargin: -10
        visible: plannerActive || opacity > 0.02
        opacity: 0
        scale: 0.98
        z: 48
        enabled: plannerActive
        transformOrigin: Item.Bottom

        transform: Translate { y: 7 - (4 * updateMapFloating.lift) }

        ShaderEffectSource {
            id: updateMapSlice
            anchors.fill: parent
            sourceItem: sceneLayer
            sourceRect: Qt.rect(updateMapFloating.x, updateMapFloating.y, updateMapFloating.width, updateMapFloating.height)
            recursive: true
            live: true
            visible: false
        }

        FastBlur {
            id: updateMapBlur
            anchors.fill: parent
            source: updateMapSlice
            radius: 16
            transparentBorder: true
            visible: updateMapFloating.plannerActive
            z: -3
        }

        OpacityMask {
            anchors.fill: parent
            source: updateMapBlur
            maskSource: Rectangle {
                width: updateMapFloating.width
                height: updateMapFloating.height
                radius: height / 2
            }
            z: -2
        }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            color: mapGlassFill
            border.color: mapGlassBorder
            border.width: 1
            z: -1
        }

        Rectangle {
            anchors.fill: parent
            radius: height / 2
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.14) }
                GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.05) }
            }
            opacity: updateMapMouse.containsMouse ? 0.30 : 0.18
            Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
        }

        Text {
            id: updateMapLabel
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -4
            text: "Update map"
            color: updateMapFloating.enabled ? textPrimary : textMuted
            font.pixelSize: 13
            font.family: "Inter"
        }

        MouseArea {
            id: updateMapMouse
            anchors.fill: parent
            enabled: updateMapFloating.enabled
            hoverEnabled: updateMapFloating.enabled
            onEntered: updateMapLabel.color = textPrimary
            onExited: updateMapLabel.color = updateMapFloating.enabled ? textPrimary : textMuted
            onPressed: updateMapFloating.scale = 0.97
            onReleased: updateMapFloating.scale = 1.0
            onClicked: { if (hasApp) app.refreshMapView(); }
        }

        states: [
            State {
                name: "shown"
                when: updateMapFloating.plannerActive
                PropertyChanges { target: updateMapFloating; opacity: 1; scale: 1.0; lift: 1 }
            },
            State {
                name: "hidden"
                when: !updateMapFloating.plannerActive
                PropertyChanges { target: updateMapFloating; opacity: 0; scale: 0.98; lift: 0 }
            }
        ]

        transitions: [
            Transition {
                from: "hidden"
                to: "shown"
                NumberAnimation { properties: "opacity,scale,lift"; duration: 240; easing.type: Easing.OutCubic }
            },
            Transition {
                from: "shown"
                to: "hidden"
                NumberAnimation { properties: "opacity,scale,lift"; duration: 220; easing.type: Easing.OutCubic }
            }
        ]
    }

    Component.onCompleted: {
        if (!hasApp || !app.cameraAvailable) currentTab = 1;
        if (hasApp) app.setVideoVisible(currentTab === 0);
    }

    DebugWindow { id: debugWindow }

    FileDialog {
        id: geojsonDialog
        title: "Import GeoJSON"
        nameFilters: ["GeoJSON (*.geojson *.json)"]
        onAccepted: { if (hasApp) app.importGeoJson(fileUrl.toLocalFile()) }
    }

    FileDialog {
        id: kmlDialog
        title: "Import KML"
        nameFilters: ["KML (*.kml)"]
        onAccepted: { if (hasApp) app.importKml(fileUrl.toLocalFile()) }
    }
}
