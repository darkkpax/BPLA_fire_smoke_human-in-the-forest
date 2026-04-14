import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import QtQuick.Controls.Material 2.15

Window {
    id: debugWindow
    width: 560
    height: 460
    minimumWidth: 500
    minimumHeight: 420
    visible: false
    title: "Bridge console"
    color: "transparent"
    flags: Qt.Dialog | Qt.WindowStaysOnTopHint

    property bool hasApp: typeof app !== "undefined" && app !== null
    property color textPrimary: "#e8edf5"
    property color textMuted: "#9aa8bb"
    property color borderColor: Qt.rgba(1, 1, 1, 0.12)
    property color softBorderColor: Qt.rgba(1, 1, 1, 0.08)
    property color glassFill: Qt.rgba(0.08, 0.08, 0.08, 0.44)
    property color glassFillStrong: Qt.rgba(0.08, 0.08, 0.08, 0.56)
    property color glassHighlight: Qt.rgba(1, 1, 1, 0.10)
    property color glassHighlightSoft: Qt.rgba(1, 1, 1, 0.04)
    property color chipOn: Qt.rgba(1, 1, 1, 0.72)
    property color chipOff: Qt.rgba(1, 1, 1, 0.28)
    property int cardRadius: 18
    property int cardPadding: 18

    Material.theme: Material.Dark
    Material.accent: "#202020"
    Material.foreground: textPrimary

    function batteryProfileIndex() {
        if (!hasApp) return 0
        var target = app.bridgeBatteryProfileId
        var model = batteryProfileBox ? batteryProfileBox.model : []
        for (var i = 0; i < model.length; i++) {
            if (model[i].value === target) return i
        }
        return 0
    }

    Component.onCompleted: batteryProfileBox.currentIndex = batteryProfileIndex()

    Shortcut {
        sequences: [StandardKey.Close]
        onActivated: debugWindow.visible = false
    }

    Connections {
        target: hasApp ? app : null
        function onBridgeBatteryProfileChanged() {
            if (batteryProfileBox) batteryProfileBox.currentIndex = batteryProfileIndex()
        }
    }

    Rectangle {
        anchors.fill: parent
        color: "#071018"

        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.05) }
                GradientStop { position: 1.0; color: "transparent" }
            }
        }

        Rectangle {
            width: 220
            height: 220
            radius: 110
            x: -70
            y: 16
            color: Qt.rgba(1, 1, 1, 0.04)
        }

        Rectangle {
            width: 180
            height: 180
            radius: 90
            x: debugWindow.width - width - 44
            y: 92
            color: Qt.rgba(1, 1, 1, 0.03)
        }

        ScrollView {
            anchors.fill: parent
            anchors.margins: 18
            clip: true
            contentWidth: availableWidth
            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

            ColumnLayout {
                width: parent.width
                spacing: 14

                Rectangle {
                    Layout.fillWidth: true
                    radius: 22
                    color: glassFillStrong
                    border.color: borderColor
                    border.width: 1
                    implicitHeight: headerColumn.implicitHeight + 28

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.03) }
                        }
                        opacity: 0.28
                    }

                    ColumnLayout {
                        id: headerColumn
                        anchors.fill: parent
                        anchors.margins: 14
                        spacing: 6

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 10

                            Rectangle {
                                width: 12
                                height: 12
                                radius: 6
                                color: hasApp && app.debugMode ? chipOn : chipOff
                                border.color: Qt.rgba(1, 1, 1, 0.16)
                                border.width: 1
                                Layout.alignment: Qt.AlignTop
                            }

                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 2

                                Text {
                                    text: "Debug console"
                                    color: textPrimary
                                    font.pixelSize: 20
                                    font.family: "Inter"
                                    font.bold: true
                                }

                                Text {
                                    text: hasApp && app.debugMode ? "Flight loop running" : "Flight loop idle"
                                    color: textMuted
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                    elide: Text.ElideRight
                                    Layout.fillWidth: true
                                }
                            }
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "Bridge and video controls grouped into one compact panel."
                            color: textMuted
                            font.pixelSize: 12
                            font.family: "Inter"
                            wrapMode: Text.WordWrap
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    radius: cardRadius
                    color: glassFill
                    border.color: borderColor
                    border.width: 1
                    implicitHeight: controlsColumn.implicitHeight + cardPadding * 2

                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        gradient: Gradient {
                            GradientStop { position: 0.0; color: glassHighlight }
                            GradientStop { position: 1.0; color: glassHighlightSoft }
                        }
                        opacity: 0.24
                    }

                    ColumnLayout {
                        id: controlsColumn
                        anchors.fill: parent
                        anchors.margins: cardPadding
                        spacing: 14

                        Text {
                            text: "Bridge mode controls"
                            color: textPrimary
                            font.pixelSize: 17
                            font.family: "Inter"
                            font.bold: true
                        }

                        Text {
                            Layout.fillWidth: true
                            text: "All controls use one capsule layout so nothing sticks out or overlaps."
                            color: textMuted
                            font.pixelSize: 12
                            font.family: "Inter"
                            wrapMode: Text.WordWrap
                        }

                        Component {
                            id: toggleRow

                            Rectangle {
                                id: toggleRoot
                                property string title: ""
                                property string subtitle: ""
                                property bool checked: false
                                property bool enabled: true
                                property var toggleAction
                                Layout.fillWidth: true
                                radius: 14
                                color: Qt.rgba(0.08, 0.08, 0.08, 0.30)
                                border.color: mouse.containsMouse ? borderColor : softBorderColor
                                border.width: 1
                                implicitHeight: 72

                                Rectangle {
                                    anchors.fill: parent
                                    radius: parent.radius
                                    gradient: Gradient {
                                        GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, mouse.containsMouse ? 0.10 : 0.06) }
                                        GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.02) }
                                    }
                                }

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.margins: 12
                                    spacing: 12

                                    ColumnLayout {
                                        Layout.fillWidth: true
                                        spacing: 4

                                        Text {
                                            Layout.fillWidth: true
                                            text: toggleRoot.title
                                            color: textPrimary
                                            font.pixelSize: 13
                                            font.family: "Inter"
                                            font.weight: Font.Medium
                                            elide: Text.ElideRight
                                        }

                                        Text {
                                            Layout.fillWidth: true
                                            visible: toggleRoot.subtitle.length > 0
                                            text: toggleRoot.subtitle
                                            color: textMuted
                                            font.pixelSize: 11
                                            font.family: "Inter"
                                            wrapMode: Text.WordWrap
                                        }
                                    }

                                    Rectangle {
                                        Layout.alignment: Qt.AlignVCenter
                                        width: 54
                                        height: 30
                                        radius: height / 2
                                        color: toggleRoot.checked ? Qt.rgba(1, 1, 1, 0.18) : Qt.rgba(1, 1, 1, 0.10)
                                        border.color: toggleRoot.checked ? Qt.rgba(1, 1, 1, 0.20) : softBorderColor
                                        border.width: 1

                                        Rectangle {
                                            width: 22
                                            height: 22
                                            radius: 11
                                            x: toggleRoot.checked ? parent.width - width - 4 : 4
                                            y: 4
                                            color: toggleRoot.enabled ? "#d7deea" : Qt.rgba(1, 1, 1, 0.25)
                                            border.color: Qt.rgba(1, 1, 1, 0.16)
                                            border.width: 1
                                            Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                                        }
                                    }
                                }

                                MouseArea {
                                    id: mouse
                                    anchors.fill: parent
                                    hoverEnabled: toggleRoot.enabled
                                    enabled: toggleRoot.enabled
                                    onClicked: {
                                        if (toggleRoot.toggleAction) toggleRoot.toggleAction()
                                    }
                                }
                            }
                        }

                        Loader {
                            Layout.fillWidth: true
                            sourceComponent: toggleRow
                            onLoaded: {
                                item.title = Qt.binding(function() { return hasApp && app.bridgeModeEnabled ? "Bridge mode ON" : "Bridge mode OFF" })
                                item.subtitle = "Simulate telemetry and camera through the bridge pipeline."
                                item.checked = Qt.binding(function() { return hasApp && app.bridgeModeEnabled })
                                item.enabled = Qt.binding(function() { return hasApp })
                                item.toggleAction = function() {
                                    if (hasApp) app.setBridgeModeEnabled(!app.bridgeModeEnabled)
                                }
                            }
                        }

                        Loader {
                            Layout.fillWidth: true
                            sourceComponent: toggleRow
                            onLoaded: {
                                item.title = Qt.binding(function() { return hasApp && app.unrealVideoMode === "h264_stream" ? "Unreal video: H.264 stream" : "Unreal video: JPEG snapshots" })
                                item.subtitle = "Available only when the Unreal backend is active."
                                item.checked = Qt.binding(function() { return hasApp && app.unrealVideoMode === "h264_stream" })
                                item.enabled = Qt.binding(function() { return hasApp && app.currentBackend === "unreal" })
                                item.toggleAction = function() {
                                    if (hasApp) app.setUnrealVideoMode(app.unrealVideoMode === "h264_stream" ? "jpeg_snapshots" : "h264_stream")
                                }
                            }
                        }

                        Loader {
                            Layout.fillWidth: true
                            sourceComponent: toggleRow
                            onLoaded: {
                                item.title = Qt.binding(function() { return hasApp && app.debugDisableDetectorDuringOrbit ? "Detector hard stop during orbit" : "Detector keeps running during orbit" })
                                item.subtitle = "Debug only. Hard-disables detector processing while orbit is active."
                                item.checked = Qt.binding(function() { return hasApp && app.debugDisableDetectorDuringOrbit })
                                item.enabled = Qt.binding(function() { return hasApp })
                                item.toggleAction = function() {
                                    if (hasApp) app.setDebugDisableDetectorDuringOrbit(!app.debugDisableDetectorDuringOrbit)
                                }
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6

                            Text {
                                text: "Drone profile"
                                color: textMuted
                                font.pixelSize: 12
                                font.family: "Inter"
                            }

                            ComboBox {
                                id: batteryProfileBox
                                Layout.fillWidth: true
                                implicitHeight: 42
                                leftPadding: 14
                                rightPadding: 38
                                topPadding: 0
                                bottomPadding: 0
                                model: [
                                    { text: "DJI Mavic 3 (77 Wh)", value: "mavic3" },
                                    { text: "DJI Mini 4 Pro (29 Wh)", value: "mini4" },
                                    { text: "DJI Matrice 30T (263 Wh)", value: "matrice30" },
                                    { text: "Autel EVO II (82 Wh)", value: "autel_evo" },
                                    { text: "Skydio X2 (49 Wh)", value: "skydio_x2" }
                                ]
                                textRole: "text"
                                valueRole: "value"

                                onActivated: {
                                    if (hasApp) app.setBridgeBatteryProfile(currentValue)
                                }

                                delegate: ItemDelegate {
                                    width: batteryProfileBox.width
                                    highlighted: batteryProfileBox.highlightedIndex === index
                                    contentItem: Text {
                                        text: modelData.text
                                        color: textPrimary
                                        font.pixelSize: 12
                                        font.family: "Inter"
                                        verticalAlignment: Text.AlignVCenter
                                        elide: Text.ElideRight
                                    }
                                    background: Rectangle {
                                        radius: 10
                                        color: highlighted ? Qt.rgba(1, 1, 1, 0.10) : "transparent"
                                    }
                                }

                                indicator: Canvas {
                                    x: batteryProfileBox.width - width - 14
                                    y: (batteryProfileBox.height - height) / 2
                                    width: 12
                                    height: 8
                                    contextType: "2d"
                                    onPaint: {
                                        context.reset()
                                        context.moveTo(0, 0)
                                        context.lineTo(width, 0)
                                        context.lineTo(width / 2, height)
                                        context.closePath()
                                        context.fillStyle = "#d7deea"
                                        context.fill()
                                    }
                                }

                                contentItem: Text {
                                    text: batteryProfileBox.displayText
                                    color: textPrimary
                                    font.pixelSize: 12
                                    font.family: "Inter"
                                    verticalAlignment: Text.AlignVCenter
                                    elide: Text.ElideRight
                                }

                                background: Rectangle {
                                    radius: 12
                                    color: Qt.rgba(0.08, 0.08, 0.08, 0.34)
                                    border.color: batteryProfileBox.popup.visible ? borderColor : softBorderColor
                                    border.width: 1

                                    Rectangle {
                                        anchors.fill: parent
                                        radius: parent.radius
                                        gradient: Gradient {
                                            GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.10) }
                                            GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.03) }
                                        }
                                        opacity: 0.22
                                    }
                                }

                                popup: Popup {
                                    y: batteryProfileBox.height + 8
                                    width: batteryProfileBox.width
                                    padding: 8
                                    implicitHeight: Math.min(contentItem.implicitHeight + 16, 220)
                                    background: Rectangle {
                                        radius: 14
                                        color: Qt.rgba(0.06, 0.07, 0.10, 0.96)
                                        border.color: softBorderColor
                                        border.width: 1
                                    }
                                    contentItem: ListView {
                                        clip: true
                                        implicitHeight: contentHeight
                                        model: batteryProfileBox.popup.visible ? batteryProfileBox.delegateModel : null
                                        currentIndex: batteryProfileBox.highlightedIndex
                                        spacing: 4
                                        ScrollBar.vertical: ScrollBar {
                                            width: 8
                                            visible: size < 1.0
                                            contentItem: Rectangle {
                                                radius: width / 2
                                                color: Qt.rgba(1, 1, 1, 0.18)
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            Layout.alignment: Qt.AlignHCenter
                            Layout.preferredWidth: Math.min(260, controlsColumn.width)
                            implicitWidth: Math.min(260, controlsColumn.width)
                            implicitHeight: 38
                            radius: implicitHeight / 2
                            color: Qt.rgba(0.08, 0.08, 0.08, 0.38)
                            border.color: borderColor
                            border.width: 1

                            Rectangle {
                                anchors.fill: parent
                                radius: parent.radius
                                gradient: Gradient {
                                    GradientStop { position: 0.0; color: Qt.rgba(1, 1, 1, 0.12) }
                                    GradientStop { position: 1.0; color: Qt.rgba(1, 1, 1, 0.04) }
                                }
                                opacity: closeMouse.containsMouse ? 0.30 : 0.18
                                Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                            }

                            Text {
                                anchors.centerIn: parent
                                text: "Close debug window"
                                color: textPrimary
                                font.pixelSize: 13
                                font.family: "Inter"
                                font.weight: Font.Medium
                            }

                            MouseArea {
                                id: closeMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: debugWindow.visible = false
                            }
                        }
                    }
                }
            }
        }
    }
}
