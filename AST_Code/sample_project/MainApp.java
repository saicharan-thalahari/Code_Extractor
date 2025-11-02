package com.example.app;

import com.example.web.AccountController;
import com.example.util.Utils;

public class MainApp {
    public static void main(String[] args) {
        AccountController ctrl = new AccountController();
        String id = Utils.uid();
        ctrl.createAndProcess(id, "Alice");
    }
}
