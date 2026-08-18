Attribute VB_Name = "Run_All_KeyVars_Integrated_FINAL_BACKUP"
' FINAL BACKUP — Run_All_KeyVars_Integrated
' Saved: 2026-08-18
' Notes: lastR=1210; extract row 70 → dest 72+MP; LOOP10=copy LOOP9;
'        EEV LOOP=1 before paste; leave on EEV at end; full Application.Calculate per LOOP
'        (pre sheet-chain optimisation). rebuildEEV flag still present but keep =0.

Sub Run_All_KeyVars_Integrated()
    Dim ws As Worksheet
    Dim wsRBC(1 To 10) As Worksheet
    Dim wsEEV As Worksheet
    Dim wsMacro As Worksheet
    Dim i As Integer, j As Integer
    Dim startMP As Integer, endMP As Integer
    Dim g As Integer, n As Integer, r As Integer, a As Integer, b As Integer
    Dim destRow As Integer
    Dim d As Variant
    Dim names As Variant
    Dim calcMode As XlCalculation
    Dim tStart As Double, tSetup As Double, tMain As Double, tTotal As Double
    Dim nMP As Integer, nCalc As Integer
    Dim mins As Long, secs As Long
    Dim lastR As Long
    Dim stopAtErr As Boolean
    Dim rebuildEEV As Boolean
    Dim qDiff As Double
    Dim stoppedEarly As Boolean
    Dim clearFromRow As Long
    Dim lastDoneMP As Integer

    startMP = Range("Start_MP").Value
    endMP = Range("End_MP").Value

    If startMP < 1 Or endMP < startMP Then
        MsgBox "Check Start_MP and End_MP.", vbExclamation
        Exit Sub
    End If

    If endMP > 24982 Then
        MsgBox "End_MP too high. Max End_MP is 24982 (result row = 72 + MP).", vbExclamation
        Exit Sub
    End If

    lastR = 1210

    stopAtErr = False
    rebuildEEV = False
    On Error Resume Next
    stopAtErr = (CLng(Range("STOP_LOOP_AT_ERROR").Value) = 1)
    rebuildEEV = (CLng(Range("EEV_REBUILD_RESERVE").Value) = 1)
    On Error GoTo 0

    If stopAtErr Then
        clearFromRow = 72 + startMP
    Else
        clearFromRow = 73
    End If

    nMP = endMP - startMP + 1
    nCalc = nMP * 12
    tStart = Timer
    stoppedEarly = False
    lastDoneMP = startMP

    names = Array("RES", "MORT", "DIS", "CI", "LPSU", "LPSD", "EXP", "CAT", "BE", "BE2")

    calcMode = Application.Calculation
    Application.ScreenUpdating = False
    Application.EnableEvents = False
    Application.DisplayStatusBar = True
    Application.Calculation = xlCalculationManual
    Application.CutCopyMode = False

    Set wsMacro = Worksheets("KEY_VAR_RBC_macro")
    wsMacro.Rows(clearFromRow & ":25000").ClearContents

    For i = 1 To 10
        On Error Resume Next
        Set wsRBC(i) = Nothing
        Set wsRBC(i) = Worksheets("KEY_VARS_RBC_" & names(i - 1))
        On Error GoTo 0

        If wsRBC(i) Is Nothing Then
            wsMacro.Copy Before:=wsMacro
            ActiveSheet.Name = "KEY_VARS_RBC_" & names(i - 1)
            Set wsRBC(i) = ActiveSheet
            If i > 1 Then
                wsRBC(i).Move After:=Worksheets("KEY_VARS_RBC_" & names(i - 2))
            End If
        End If

        wsRBC(i).Range("B8").Value = i
        wsRBC(i).Tab.Color = RGB(255, 0, 0)
        wsRBC(i).Rows(clearFromRow & ":25000").ClearContents
    Next i

    Set wsEEV = Worksheets("KEY_VAR_EEV")
    wsEEV.Rows(clearFromRow & ":25000").ClearContents

    Set ws = Worksheets("RBC_Reserves(Loop_all)")

    g = ws.Range("Gross_Res_Start_col").Value
    n = ws.Range("Net_Res_Start_col").Value
    r = ws.Range("RI_Res_Start_col").Value
    a = ws.Range("LC2A_Res_Start_col").Value
    b = ws.Range("LC2B_Res_Start_col").Value

    ws.Range(ws.Cells(7, g + 1), ws.Cells(lastR, g + 10)).ClearContents
    ws.Range(ws.Cells(7, n + 1), ws.Cells(lastR, n + 10)).ClearContents
    ws.Range(ws.Cells(7, r + 1), ws.Cells(lastR, r + 10)).ClearContents
    ws.Range(ws.Cells(7, a + 1), ws.Cells(lastR, a + 10)).ClearContents
    ws.Range(ws.Cells(7, b + 1), ws.Cells(lastR, b + 10)).ClearContents

    tSetup = Timer - tStart
    If tSetup < 0 Then tSetup = tSetup + 86400#

    For j = startMP To endMP
        Range("Model_Point").Value = j
        destRow = 72 + j

        Range("Val_Model").Value = "RBC"
        Application.Calculate

        For i = 1 To 9
            Application.StatusBar = "Key Vars: MP " & j & " of " & endMP & _
                " (" & j - startMP + 1 & "/" & nMP & ") | LOOP " & i & "/9 (+10=copy9)"
            DoEvents

            Range("LOOP").Value = i
            Application.Calculate

            If Not rebuildEEV Then
                d = ws.Range(ws.Cells(7, g), ws.Cells(lastR, g)).Value
                ws.Range(ws.Cells(7, g + i), ws.Cells(lastR, g + i)).Value = d

                d = ws.Range(ws.Cells(7, n), ws.Cells(lastR, n)).Value
                ws.Range(ws.Cells(7, n + i), ws.Cells(lastR, n + i)).Value = d

                d = ws.Range(ws.Cells(7, r), ws.Cells(lastR, r)).Value
                ws.Range(ws.Cells(7, r + i), ws.Cells(lastR, r + i)).Value = d

                d = ws.Range(ws.Cells(7, a), ws.Cells(lastR, a)).Value
                ws.Range(ws.Cells(7, a + i), ws.Cells(lastR, a + i)).Value = d

                d = ws.Range(ws.Cells(7, b), ws.Cells(lastR, b)).Value
                ws.Range(ws.Cells(7, b + i), ws.Cells(lastR, b + i)).Value = d
            End If

            wsRBC(i).Rows(destRow).Value = wsRBC(i).Rows(70).Value
        Next i

        Application.StatusBar = "Key Vars: MP " & j & " of " & endMP & _
            " (" & j - startMP + 1 & "/" & nMP & ") | LOOP 10 = copy LOOP 9"
        DoEvents

        If Not rebuildEEV Then
            ws.Range(ws.Cells(7, g + 10), ws.Cells(lastR, g + 10)).Value = _
                ws.Range(ws.Cells(7, g + 9), ws.Cells(lastR, g + 9)).Value
            ws.Range(ws.Cells(7, n + 10), ws.Cells(lastR, n + 10)).Value = _
                ws.Range(ws.Cells(7, n + 9), ws.Cells(lastR, n + 9)).Value
            ws.Range(ws.Cells(7, r + 10), ws.Cells(lastR, r + 10)).Value = _
                ws.Range(ws.Cells(7, r + 9), ws.Cells(lastR, r + 9)).Value
            ws.Range(ws.Cells(7, a + 10), ws.Cells(lastR, a + 10)).Value = _
                ws.Range(ws.Cells(7, a + 9), ws.Cells(lastR, a + 9)).Value
            ws.Range(ws.Cells(7, b + 10), ws.Cells(lastR, b + 10)).Value = _
                ws.Range(ws.Cells(7, b + 9), ws.Cells(lastR, b + 9)).Value
        End If
        wsRBC(10).Rows(destRow).Value = wsRBC(9).Rows(destRow).Value

        Range("Val_Model").Value = "EEV"

        If rebuildEEV Then
            For i = 1 To 9
                Application.StatusBar = "Key Vars: MP " & j & " of " & endMP & _
                    " (" & j - startMP + 1 & "/" & nMP & ") | EEV LOOP " & i & "/9"
                DoEvents

                Range("LOOP").Value = i
                Application.Calculate

                d = ws.Range(ws.Cells(7, g), ws.Cells(lastR, g)).Value
                ws.Range(ws.Cells(7, g + i), ws.Cells(lastR, g + i)).Value = d

                d = ws.Range(ws.Cells(7, n), ws.Cells(lastR, n)).Value
                ws.Range(ws.Cells(7, n + i), ws.Cells(lastR, n + i)).Value = d

                d = ws.Range(ws.Cells(7, r), ws.Cells(lastR, r)).Value
                ws.Range(ws.Cells(7, r + i), ws.Cells(lastR, r + i)).Value = d

                d = ws.Range(ws.Cells(7, a), ws.Cells(lastR, a)).Value
                ws.Range(ws.Cells(7, a + i), ws.Cells(lastR, a + i)).Value = d

                d = ws.Range(ws.Cells(7, b), ws.Cells(lastR, b)).Value
                ws.Range(ws.Cells(7, b + i), ws.Cells(lastR, b + i)).Value = d
            Next i

            ws.Range(ws.Cells(7, g + 10), ws.Cells(lastR, g + 10)).Value = _
                ws.Range(ws.Cells(7, g + 9), ws.Cells(lastR, g + 9)).Value
            ws.Range(ws.Cells(7, n + 10), ws.Cells(lastR, n + 10)).Value = _
                ws.Range(ws.Cells(7, n + 9), ws.Cells(lastR, n + 9)).Value
            ws.Range(ws.Cells(7, r + 10), ws.Cells(lastR, r + 10)).Value = _
                ws.Range(ws.Cells(7, r + 9), ws.Cells(lastR, r + 9)).Value
            ws.Range(ws.Cells(7, a + 10), ws.Cells(lastR, a + 10)).Value = _
                ws.Range(ws.Cells(7, a + 9), ws.Cells(lastR, a + 9)).Value
            ws.Range(ws.Cells(7, b + 10), ws.Cells(lastR, b + 10)).Value = _
                ws.Range(ws.Cells(7, b + 9), ws.Cells(lastR, b + 9)).Value
        End If

        Application.StatusBar = "Key Vars: MP " & j & " of " & endMP & _
            " (" & j - startMP + 1 & "/" & nMP & ") | EEV"
        DoEvents

        Range("LOOP").Value = 1
        Application.Calculate
        wsEEV.Rows(destRow).Value = wsEEV.Rows(70).Value
        lastDoneMP = j

        If stopAtErr Then
            If IsNumeric(wsEEV.Range("Q70").Value) Then
                qDiff = CDbl(wsEEV.Range("Q70").Value)
                If qDiff < -2# Or qDiff > 2# Then
                    stoppedEarly = True
                    Exit For
                End If
            Else
                stoppedEarly = True
                Exit For
            End If
        End If
    Next j

    Range("Model_Point").Value = lastDoneMP
    Range("LOOP").Value = 1
    Range("Val_Model").Value = "EEV"
    Application.Calculate

    Application.Calculation = calcMode
    Application.EnableEvents = True
    Application.ScreenUpdating = True
    Application.StatusBar = False

    tTotal = Timer - tStart
    If tTotal < 0 Then tTotal = tTotal + 86400#
    tMain = tTotal - tSetup

    mins = Int(tTotal \ 60)
    secs = CLng(tTotal - mins * 60)

    Worksheets("MPF").Range("H9").Value = mins & " min " & secs & " sec"

    wsEEV.Activate

    If stoppedEarly Then
        MsgBox "STOPPED at Model_Point " & j & vbCrLf & _
               "KEY_VAR_EEV!Q70 = " & wsEEV.Range("Q70").Value & vbCrLf & _
               "(outside -2 to +2). Prophet vs Excel difference too large." & vbCrLf & _
               "Earlier MPs kept. Set Start_MP=" & j & " to resume." & vbCrLf & _
               "Time so far: " & mins & " min " & secs & " sec", vbExclamation
    Else
        MsgBox "Done. Time taken: " & mins & " min " & secs & " sec" & vbCrLf & _
               "EEV_REBUILD_RESERVE=" & IIf(rebuildEEV, 1, 0) & vbCrLf & _
               "LOOP 10 = copy of LOOP 9. Left on EEV / MP " & lastDoneMP & ".", vbInformation
    End If
End Sub
