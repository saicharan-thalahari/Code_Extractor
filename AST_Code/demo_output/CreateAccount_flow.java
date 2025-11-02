import com.example.service.AccountService;


// === 1. CreateAccount  (from C:\Users\chara\OneDrive\Desktop\AST_Code\sample_project\CreateAccount.java lines 5-14)

package com.example.app;

import com.example.service.AccountService;

public class CreateAccount {


// ---- method: create

void create() {
        AccountService svc = new AccountService();
        svc.openAccount();
    }



// === 2. AccountService  (from C:\Users\chara\OneDrive\Desktop\AST_Code\sample_project\AccountService.java lines 3-9)

package com.example.service;

public class AccountService {


// ---- method: openAccount

void openAccount() {
        Helper.log("opening");
    }



// === 3. Helper  (from C:\Users\chara\OneDrive\Desktop\AST_Code\sample_project\Helper.java lines 3-9)

package com.example.util;

public class Helper {


// ---- method: log

void log(String s) {
        System.out.println(s);
    }


