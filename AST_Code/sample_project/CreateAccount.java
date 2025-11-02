package com.example.app;

import com.example.service.AccountService;

public class CreateAccount {
    public void create() {
        AccountService svc = new AccountService();
        svc.openAccount();
    }
}
